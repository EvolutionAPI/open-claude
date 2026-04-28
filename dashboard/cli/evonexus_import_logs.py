"""evonexus-import-logs — backfill file-based logs into Postgres.

Use case: workspace migrated to PG via db-migrate + import-configs, but
historical logs remain in files. This CLI reads the file layout and
populates the native logs tables (created by migration 0011).

Idempotent:
  - chat sessions:          agent_chat_sessions.id PK, ON CONFLICT DO NOTHING
  - chat messages:          agent_chat_messages.id PK, ON CONFLICT DO NOTHING
  - daily_outputs:          (date, kind) checked before insert; --force re-inserts
  - meeting_transcripts:    fathom_id UNIQUE, ON CONFLICT DO NOTHING
  - plugin_hook_runs:       (slug, hook_name, started_at) checked before insert
  - brain_repo_transcripts: (project_slug, session_id) UNIQUE, ON CONFLICT DO NOTHING
  - workspace_mutations:    insert-only (append log, no natural key)
  - routine_runs:           insert-only (append log, no natural key)

Refuses to run against SQLite — PG-only tool.

Sources imported:
  workspace/ADWs/logs/chat/*.jsonl         → agent_chat_sessions + agent_chat_messages
  workspace/daily-logs/[C] *.{md,html}    → daily_outputs
  workspace/meetings/fathom/**/*.json      → meeting_transcripts
  workspace/ADWs/logs/plugins/*.log        → plugin_hook_runs
  memory/raw-transcripts/*/*.jsonl         → brain_repo_transcripts
  workspace/ADWs/logs/workspace-mutations.jsonl → workspace_mutations
  workspace/ADWs/logs/routines/*.log       → routine_runs

SKIPPED (already covered by heartbeat_runs):
  workspace/ADWs/logs/heartbeats/*.jsonl

Usage:
  evonexus-import-logs [--dry-run] [--force] [--verbose]
                       [--source {chat,daily,meetings,plugin-hooks,brain,audit,routines,all}]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

# ---------------------------------------------------------------------------
# sys.path bootstrap — dashboard/backend must be importable.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_BACKEND_DIR = _HERE.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

WORKSPACE_ROOT = _HERE.parents[2]

CHAT_DIR = WORKSPACE_ROOT / "workspace" / "ADWs" / "logs" / "chat"
DAILY_LOGS_DIR = WORKSPACE_ROOT / "workspace" / "daily-logs"
FATHOM_DIR = WORKSPACE_ROOT / "workspace" / "meetings" / "fathom"
PLUGIN_LOGS_DIR = WORKSPACE_ROOT / "workspace" / "ADWs" / "logs" / "plugins"
BRAIN_REPO_DIR = WORKSPACE_ROOT / "memory" / "raw-transcripts"
WORKSPACE_AUDIT_FILE = WORKSPACE_ROOT / "workspace" / "ADWs" / "logs" / "workspace-mutations.jsonl"
ROUTINE_LOGS_DIR = WORKSPACE_ROOT / "workspace" / "ADWs" / "logs" / "routines"


# ---------------------------------------------------------------------------
# Stats accumulator
# ---------------------------------------------------------------------------

class _Stats:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def add(self, category: str, n: int = 1) -> None:
        self.counts[category] = self.counts.get(category, 0) + n

    def total(self) -> int:
        return sum(self.counts.values())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_ts(v: object) -> str | None:
    """Convert various timestamp formats to ISO-8601 string for PG TIMESTAMPTZ."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # Epoch milliseconds if > 1e12, else seconds
        secs = v / 1000 if v > 1e12 else v
        return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    s = str(v)
    return s if s else None


# ---------------------------------------------------------------------------
# Source: chat JSONL  →  agent_chat_sessions + agent_chat_messages
# ---------------------------------------------------------------------------

def import_chat(args: argparse.Namespace, stats: _Stats) -> None:
    """Read chat JSONL files and import sessions + messages."""
    if not CHAT_DIR.exists():
        if args.verbose:
            print("  chat: directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    files = sorted(CHAT_DIR.glob("*.jsonl"))
    if not files:
        if args.verbose:
            print("  chat: no .jsonl files found")
        return

    if args.dry_run:
        print(f"  chat: would process {len(files)} file(s)")
        # Count lines as approximate message count
        total_lines = 0
        for f in files:
            try:
                total_lines += sum(1 for ln in open(f, encoding="utf-8") if ln.strip())
            except OSError:
                pass
        print(f"  chat: ~{total_lines} message lines across {len(files)} session(s)")
        stats.add("chat_sessions", len(files))
        stats.add("chat_messages", total_lines)
        return

    engine = get_engine()

    for jsonl_file in files:
        # Filename pattern: {agentName}_{shortId}.jsonl
        m = re.match(r"^(.+)_([0-9a-f]+)\.jsonl$", jsonl_file.name)
        if m:
            agent_name = m.group(1).replace("_", "-")
            short_id = m.group(2)
        else:
            agent_name = jsonl_file.stem
            short_id = "0"

        # Synthesize stable session UUID from file path
        synth_session_id = str(uuid5(NAMESPACE_URL, f"chat:{agent_name}:{short_id}"))

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent_chat_sessions (id, agent_name, last_activity_at, created_at)
                VALUES (:sid, :agent, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """), {"sid": synth_session_id, "agent": agent_name})

            msg_count = 0
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Rewind marker — soft-delete the referenced message
                        if msg.get("type") == "rewind":
                            target = msg.get("at")
                            if target:
                                conn.execute(text("""
                                    UPDATE agent_chat_messages
                                    SET rewound_at = NOW()
                                    WHERE id = :uuid AND rewound_at IS NULL
                                """), {"uuid": target})
                            continue

                        msg_uuid = msg.get("uuid")
                        if not msg_uuid:
                            # Synthesize stable id from session + line fingerprint
                            msg_uuid = str(uuid5(
                                NAMESPACE_URL,
                                f"{synth_session_id}:{msg.get('ts')}:{msg.get('role')}:{line[:200]}",
                            ))

                        blocks = msg.get("blocks")
                        files_field = msg.get("files")
                        conn.execute(text("""
                            INSERT INTO agent_chat_messages
                                (id, session_id, role, text, blocks, files, ts)
                            VALUES (:id, :sid, :role, :text, :blocks, :files,
                                    COALESCE(CAST(:ts AS TIMESTAMPTZ), NOW()))
                            ON CONFLICT (id) DO NOTHING
                        """), {
                            "id": msg_uuid,
                            "sid": synth_session_id,
                            "role": msg.get("role", "user"),
                            "text": msg.get("text"),
                            "blocks": json.dumps(blocks) if blocks is not None else None,
                            "files": json.dumps(files_field) if files_field is not None else None,
                            "ts": _safe_ts(msg.get("ts")),
                        })
                        msg_count += 1
            except OSError as exc:
                print(f"  WARNING: cannot read {jsonl_file.name}: {exc}")
                continue

        stats.add("chat_sessions", 1)
        stats.add("chat_messages", msg_count)
        if args.verbose:
            print(f"    chat session {jsonl_file.name}: {msg_count} message(s)")


# ---------------------------------------------------------------------------
# Source: daily-logs  →  daily_outputs
# ---------------------------------------------------------------------------

# CHECK constraint values for kind column
_KIND_ALLOWED = {
    "morning", "eod", "dashboard", "email-triage", "todoist-review",
    "weekly", "memory-sync", "memory-lint", "health", "trends", "strategy",
    "community", "licensing", "social", "meeting-summary", "custom",
}

_KIND_MAP: dict[str, str] = {
    "morning": "morning",
    "eod": "eod",
    "dashboard": "dashboard",
    "email-triage": "email-triage",
    "todoist-review": "todoist-review",
    "weekly": "weekly",
    "memory-sync": "memory-sync",
    "memory-lint": "memory-lint",
    "health": "health",
    "trends": "trends",
    "strategy-digest": "strategy",
    "strategy": "strategy",
    "community-pulse": "community",
    "community": "community",
    "licensing": "licensing",
    "social": "social",
    "meeting-summary": "meeting-summary",
}

# Pattern: [C] YYYY-MM-DD-{kind}.{ext}  or  [C] YYYY-MM-DD.{ext} (plain eod)
_DAILY_RE = re.compile(r"^\[C\]\s+(\d{4}-\d{2}-\d{2})(?:-(.+?))?\.(md|html)$")


def import_daily_outputs(args: argparse.Namespace, stats: _Stats) -> None:
    if not DAILY_LOGS_DIR.exists():
        if args.verbose:
            print("  daily: directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    candidates = [
        f for f in sorted(DAILY_LOGS_DIR.iterdir())
        if f.is_file() and f.suffix in (".md", ".html") and _DAILY_RE.match(f.name)
    ]

    if not candidates:
        if args.verbose:
            print("  daily: no matching files found")
        return

    if args.dry_run:
        print(f"  daily: would process {len(candidates)} file(s)")
        stats.add("daily_outputs", len(candidates))
        return

    engine = get_engine()
    imported = 0

    for f in candidates:
        m = _DAILY_RE.match(f.name)
        if not m:
            continue
        date_str = m.group(1)
        raw_kind = m.group(2) or "eod"
        fmt = m.group(3)

        canonical_kind = _KIND_MAP.get(raw_kind, "custom")
        # Ensure it satisfies the CHECK constraint
        if canonical_kind not in _KIND_ALLOWED:
            canonical_kind = "custom"

        with engine.begin() as conn:
            existing = conn.execute(text("""
                SELECT id FROM daily_outputs
                WHERE date = CAST(:d AS DATE) AND kind = :k AND format = :f
                LIMIT 1
            """), {"d": date_str, "k": canonical_kind, "f": fmt}).fetchone()

            if existing and not args.force:
                if args.verbose:
                    print(f"    SKIP daily {f.name} (already in DB)")
                continue

            try:
                content = f.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"  WARNING: cannot read {f.name}: {exc}")
                continue

            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)

            if existing:
                # --force: update content
                conn.execute(text("""
                    UPDATE daily_outputs
                    SET content = :c, created_at = :ct
                    WHERE id = :id
                """), {"c": content, "ct": mtime, "id": existing[0]})
                if args.verbose:
                    print(f"    UPDATE daily {f.name} (--force)")
            else:
                conn.execute(text("""
                    INSERT INTO daily_outputs (date, kind, format, content, created_at)
                    VALUES (CAST(:d AS DATE), :k, :f, :c, :ct)
                """), {
                    "d": date_str, "k": canonical_kind, "f": fmt,
                    "c": content, "ct": mtime,
                })
                if args.verbose:
                    print(f"    INSERT daily {f.name}")

        imported += 1

    stats.add("daily_outputs", imported)


# ---------------------------------------------------------------------------
# Source: meetings/fathom/**/*.json  →  meeting_transcripts
# ---------------------------------------------------------------------------

def import_meetings(args: argparse.Namespace, stats: _Stats) -> None:
    if not FATHOM_DIR.exists():
        if args.verbose:
            print("  meetings: fathom directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    # Meetings live in dated subdirs: fathom/YYYY-MM-DD/*.json
    all_json = sorted(FATHOM_DIR.rglob("*.json"))
    if not all_json:
        if args.verbose:
            print("  meetings: no JSON files found")
        return

    if args.dry_run:
        print(f"  meetings: would process {len(all_json)} file(s)")
        stats.add("meetings", len(all_json))
        return

    engine = get_engine()
    imported = 0

    for f in all_json:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARNING: cannot parse {f.name}: {exc}")
            continue

        # Use recording_id as fathom_id (Fathom API field), fallback to stem
        fathom_id = str(payload.get("recording_id") or payload.get("id") or f.stem)
        title = payload.get("title") or payload.get("meeting_title") or f.stem
        started_at = payload.get("recording_start_time") or payload.get("scheduled_start_time")
        ended_at = payload.get("recording_end_time") or payload.get("scheduled_end_time")
        attendees = payload.get("calendar_invitees") or payload.get("attendees")

        # Look for summary in raw/ sibling directory (transcript .md files)
        # Pattern: raw/{project}/{date}__{...}__{recording_id}.transcript.md
        summary: str | None = None
        raw_root = FATHOM_DIR.parent / "raw"
        if raw_root.exists():
            for md in raw_root.rglob(f"*{fathom_id}*.transcript.md"):
                try:
                    summary = md.read_text(encoding="utf-8")
                except OSError:
                    pass
                break

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO meeting_transcripts
                    (fathom_id, title, started_at, ended_at, attendees,
                     transcript_full, summary, raw_payload, synced_at)
                VALUES (:fid, :title, CAST(:start AS TIMESTAMPTZ),
                        CAST(:end AS TIMESTAMPTZ), :att,
                        NULL, :summary, :raw, NOW())
                ON CONFLICT (fathom_id) DO NOTHING
            """), {
                "fid": fathom_id,
                "title": title,
                "start": _safe_ts(started_at),
                "end": _safe_ts(ended_at),
                "att": json.dumps(attendees) if attendees is not None else None,
                "summary": summary,
                "raw": json.dumps(payload),
            })

        imported += 1
        if args.verbose:
            print(f"    meeting {fathom_id}: {title}")

    stats.add("meetings", imported)


# ---------------------------------------------------------------------------
# Source: plugins/*.log  →  plugin_hook_runs
# ---------------------------------------------------------------------------

# Pattern: {slug}-{hook_name}-{YYYYMMDDTHHMMSS}.log
_PLUGIN_LOG_RE = re.compile(r"^(.+?)-(.+?)-(\d{8}T\d{6})\.log$")


def import_plugin_hooks(args: argparse.Namespace, stats: _Stats) -> None:
    if not PLUGIN_LOGS_DIR.exists():
        if args.verbose:
            print("  plugin-hooks: directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    files = sorted(PLUGIN_LOGS_DIR.glob("*.log"))
    if not files:
        if args.verbose:
            print("  plugin-hooks: no .log files found")
        return

    parseable = [f for f in files if _PLUGIN_LOG_RE.match(f.name)]
    if args.dry_run:
        print(f"  plugin-hooks: would process {len(parseable)} of {len(files)} file(s)")
        stats.add("plugin_hook_runs", len(parseable))
        return

    engine = get_engine()
    imported = 0

    for f in parseable:
        m = _PLUGIN_LOG_RE.match(f.name)
        if not m:
            continue
        slug, hook_name, ts_str = m.group(1), m.group(2), m.group(3)
        try:
            started_at = datetime.strptime(ts_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        try:
            content = f.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  WARNING: cannot read {f.name}: {exc}")
            continue

        stdout, stderr = content, ""
        if "=== stderr ===" in content:
            stdout, stderr = content.split("=== stderr ===", 1)

        with engine.begin() as conn:
            existing = conn.execute(text("""
                SELECT id FROM plugin_hook_runs
                WHERE slug = :s AND hook_name = :h
                  AND started_at = CAST(:t AS TIMESTAMPTZ)
                LIMIT 1
            """), {"s": slug, "h": hook_name, "t": started_at.isoformat()}).fetchone()

            if existing and not args.force:
                if args.verbose:
                    print(f"    SKIP plugin-hook {f.name} (already in DB)")
                continue

            if existing:
                conn.execute(text("""
                    UPDATE plugin_hook_runs
                    SET stdout = :out, stderr = :err
                    WHERE id = :id
                """), {"out": stdout[:1_048_576], "err": stderr[:1_048_576], "id": existing[0]})
                if args.verbose:
                    print(f"    UPDATE plugin-hook {f.name} (--force)")
            else:
                conn.execute(text("""
                    INSERT INTO plugin_hook_runs
                        (slug, hook_name, started_at, stdout, stderr, exit_code)
                    VALUES (:s, :h, CAST(:t AS TIMESTAMPTZ), :out, :err, NULL)
                """), {
                    "s": slug, "h": hook_name,
                    "t": started_at.isoformat(),
                    "out": stdout[:1_048_576],
                    "err": stderr[:1_048_576],
                })
                if args.verbose:
                    print(f"    INSERT plugin-hook {f.name}")

        imported += 1

    stats.add("plugin_hook_runs", imported)


# ---------------------------------------------------------------------------
# Source: memory/raw-transcripts/*/*.jsonl  →  brain_repo_transcripts
# ---------------------------------------------------------------------------

def import_brain_repo(args: argparse.Namespace, stats: _Stats) -> None:
    if not BRAIN_REPO_DIR.exists():
        if args.verbose:
            print("  brain: directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    all_jsonl = sorted(BRAIN_REPO_DIR.rglob("*.jsonl"))
    if not all_jsonl:
        if args.verbose:
            print("  brain: no .jsonl files found")
        return

    if args.dry_run:
        print(f"  brain: would process {len(all_jsonl)} file(s)")
        stats.add("brain_repo_transcripts", len(all_jsonl))
        return

    engine = get_engine()
    imported = 0

    for jsonl_file in all_jsonl:
        # project_slug = immediate parent directory name
        project_slug = jsonl_file.parent.name
        session_id = jsonl_file.stem

        try:
            content = jsonl_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  WARNING: cannot read {jsonl_file}: {exc}")
            continue

        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO brain_repo_transcripts
                    (project_slug, session_id, source_path, content, mtime, mirrored_at)
                VALUES (:slug, :sid, :src, :content, CAST(:mtime AS TIMESTAMPTZ), NOW())
                ON CONFLICT (project_slug, session_id) DO NOTHING
            """), {
                "slug": project_slug,
                "sid": session_id,
                "src": str(jsonl_file),
                "content": content,
                "mtime": mtime.isoformat(),
            })

        imported += 1
        if args.verbose:
            print(f"    brain {project_slug}/{session_id}")

    stats.add("brain_repo_transcripts", imported)


# ---------------------------------------------------------------------------
# Source: workspace-mutations.jsonl  →  workspace_mutations
# ---------------------------------------------------------------------------

def import_workspace_audit(args: argparse.Namespace, stats: _Stats) -> None:
    if not WORKSPACE_AUDIT_FILE.exists():
        if args.verbose:
            print("  audit: workspace-mutations.jsonl not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    if args.dry_run:
        count = sum(
            1 for ln in open(WORKSPACE_AUDIT_FILE, encoding="utf-8") if ln.strip()
        )
        print(f"  audit: would process {count} line(s)")
        stats.add("workspace_mutations", count)
        return

    engine = get_engine()
    imported = 0

    with engine.begin() as conn:
        try:
            with open(WORKSPACE_AUDIT_FILE, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    extra = entry.get("extra")
                    raw_uid = entry.get("user_id")
                    # Resolve user_id FK — use NULL if user not present in DB
                    resolved_uid: int | None = None
                    if raw_uid is not None:
                        row = conn.execute(
                            text("SELECT id FROM users WHERE id = :uid LIMIT 1"),
                            {"uid": raw_uid},
                        ).fetchone()
                        resolved_uid = row[0] if row else None
                    conn.execute(text("""
                        INSERT INTO workspace_mutations
                            (ts, role, op, path, result, extra, user_id)
                        VALUES (CAST(:ts AS TIMESTAMPTZ), :role, :op, :path, :result, :extra, :uid)
                    """), {
                        "ts": entry.get("ts"),
                        "role": entry.get("role"),
                        "op": entry.get("op", "unknown"),
                        "path": entry.get("path", ""),
                        "result": entry.get("result", "ok"),
                        "extra": json.dumps(extra) if extra is not None else None,
                        "uid": resolved_uid,
                    })
                    imported += 1
        except OSError as exc:
            print(f"  WARNING: cannot read workspace-mutations.jsonl: {exc}")

    stats.add("workspace_mutations", imported)
    if args.verbose:
        print(f"  audit: {imported} row(s) inserted")


# ---------------------------------------------------------------------------
# Source: routines/*.log  →  routine_runs
# ---------------------------------------------------------------------------

# Pattern: {slug}-{YYYYMMDDTHHMMSS}.log
_ROUTINE_LOG_RE = re.compile(r"^(.+?)-(\d{8}T\d{6})\.log$")


def import_routine_runs(args: argparse.Namespace, stats: _Stats) -> None:
    if not ROUTINE_LOGS_DIR.exists():
        if args.verbose:
            print("  routines: directory not found — skipping")
        return

    from sqlalchemy import text
    from db.engine import get_engine

    # Verify table exists
    engine = get_engine()
    with engine.connect() as conn:
        has_table = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'routine_runs'
            )
        """)).scalar()
    if not has_table:
        if args.verbose:
            print("  routines: routine_runs table not found — skipping")
        return

    files = sorted(ROUTINE_LOGS_DIR.glob("*.log"))
    parseable = [f for f in files if _ROUTINE_LOG_RE.match(f.name)]
    if not parseable:
        if args.verbose:
            print("  routines: no matching .log files found")
        return

    if args.dry_run:
        print(f"  routines: would process {len(parseable)} of {len(files)} file(s)")
        stats.add("routine_runs", len(parseable))
        return

    imported = 0
    with engine.begin() as conn:
        for f in parseable:
            m = _ROUTINE_LOG_RE.match(f.name)
            if not m:
                continue
            slug, ts_str = m.group(1), m.group(2)
            try:
                started_at = datetime.strptime(ts_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            try:
                content = f.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"  WARNING: cannot read {f.name}: {exc}")
                continue

            stdout, stderr = content, ""
            if "=== stderr ===" in content:
                stdout, stderr = content.split("=== stderr ===", 1)

            conn.execute(text("""
                INSERT INTO routine_runs
                    (routine_slug, started_at, stdout, stderr, exit_code, triggered_by)
                VALUES (:slug, CAST(:t AS TIMESTAMPTZ), :out, :err, NULL, 'scheduler')
            """), {
                "slug": slug,
                "t": started_at.isoformat(),
                "out": stdout[:1_048_576],
                "err": stderr[:1_048_576],
            })
            imported += 1
            if args.verbose:
                print(f"    routine {slug} @ {ts_str}")

    stats.add("routine_runs", imported)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_SOURCES = ("chat", "daily", "meetings", "plugin-hooks", "brain", "audit", "routines", "all")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill file-based logs into Postgres. "
            "Run after 'make db-upgrade' when logs still live in files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be imported; write nothing.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing rows where natural key matches.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each row as it is processed.")
    parser.add_argument(
        "--source",
        choices=_SOURCES,
        default="all",
        help="Import only one source category (default: all).",
    )
    args = parser.parse_args()

    # PG-only guard
    from config_store import get_dialect
    if get_dialect() != "postgresql":
        print("ERROR: evonexus-import-logs only runs against Postgres.")
        print("Set DATABASE_URL=postgresql://... before running.")
        return 1

    if args.dry_run:
        print("=== DRY RUN — no data will be written ===")
        print()

    stats = _Stats()
    src = args.source

    if src in ("chat", "all"):
        print("chat → agent_chat_sessions + agent_chat_messages")
        import_chat(args, stats)

    if src in ("daily", "all"):
        print("daily → daily_outputs")
        import_daily_outputs(args, stats)

    if src in ("meetings", "all"):
        print("meetings → meeting_transcripts")
        import_meetings(args, stats)

    if src in ("plugin-hooks", "all"):
        print("plugin-hooks → plugin_hook_runs")
        import_plugin_hooks(args, stats)

    if src in ("brain", "all"):
        print("brain → brain_repo_transcripts")
        import_brain_repo(args, stats)

    if src in ("audit", "all"):
        print("audit → workspace_mutations")
        import_workspace_audit(args, stats)

    if src in ("routines", "all"):
        print("routines → routine_runs")
        import_routine_runs(args, stats)

    print()
    action = "would be " if args.dry_run else ""
    print(f"Import complete. {stats.total()} rows {action}imported.")
    for cat, n in sorted(stats.counts.items()):
        print(f"  {cat}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
