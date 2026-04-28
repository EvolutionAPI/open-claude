"""evonexus-import-configs — imports file-based configs into Postgres.

Use case: user already ran ``make db-migrate`` (core data in PG) but configs
are still in files (workspace.yaml, providers.json, heartbeats.yaml,
routines.yaml). This tool populates runtime_configs, llm_providers, heartbeats
(with source_plugin=NULL for core), and routine_definitions from those files.

Idempotent — running twice does not duplicate rows.

Usage::

    evonexus-import-configs [--dry-run] [--force] [--verbose]

Flags
-----
--dry-run
    Analyse what would be imported and print a report; write nothing.
--force
    Overwrite DB values that diverge from YAML (default: skip with warning).
--verbose
    Print each individual key/row as it is processed.

Divergence detection scope
--------------------------
Workspace keys and providers receive explicit divergence detection (they are
editable in the UI and humans sometimes change them in-DB before importing).
Heartbeats and routines use INSERT-or-skip semantics (idempotent upsert);
``--force`` on those paths triggers an update pass after initial insert.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# sys.path bootstrap — dashboard/backend must be importable.
# Mirror pattern from plugin_loader.py:472-475.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_BACKEND_DIR = _HERE.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import yaml  # noqa: E402

WORKSPACE = _HERE.parents[2]
CONFIG_DIR = WORKSPACE / "config"
PLUGINS_DIR = WORKSPACE / "plugins"

# ---------------------------------------------------------------------------
# Summary accumulator
# ---------------------------------------------------------------------------

class _Summary:
    def __init__(self) -> None:
        self.workspace_total: int = 0
        self.workspace_inserted: int = 0
        self.workspace_skipped: int = 0
        self.workspace_updated: int = 0
        self.providers_total: int = 0
        self.providers_inserted: int = 0
        self.providers_skipped: int = 0
        self.providers_updated: int = 0
        self.active_provider_written: bool = False
        self.heartbeats_core: int = 0
        self.routines_core: int = 0
        self.plugins: dict[str, dict[str, int]] = {}  # slug -> {heartbeats, routines}

    def total_rows(self) -> int:
        t = (
            self.workspace_inserted
            + self.workspace_updated
            + self.providers_inserted
            + self.providers_updated
            + int(self.active_provider_written)
            + self.heartbeats_core
            + self.routines_core
        )
        for counts in self.plugins.values():
            t += counts.get("heartbeats", 0) + counts.get("routines", 0)
        return t


# ---------------------------------------------------------------------------
# Phase 1 — workspace.yaml → runtime_configs
# ---------------------------------------------------------------------------

def _import_workspace(args: argparse.Namespace, summary: _Summary, dry_run: bool) -> None:
    workspace_yaml = CONFIG_DIR / "workspace.yaml"
    if not workspace_yaml.exists():
        if args.verbose:
            print("  workspace.yaml not found — skipping workspace import")
        return

    data = yaml.safe_load(workspace_yaml.read_text(encoding="utf-8")) or {}

    # Flatten via the same algorithm as config_store._flatten()
    def _flatten(d: dict, parent: str) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent}.{k}"
            if isinstance(v, dict):
                out.extend(_flatten(v, new_key))
            else:
                out.append((new_key, v))
        return out

    # Use the file stem as root (matches config_store._get_from_yaml behaviour)
    pairs = _flatten(data, workspace_yaml.stem)
    summary.workspace_total = len(pairs)

    if dry_run:
        print(f"  workspace: would import {len(pairs)} keys")
        return

    from config_store import get_config, set_config

    for key, value in pairs:
        db_val = get_config(key)
        if db_val is None:
            # Key absent in DB — insert unconditionally
            if args.verbose:
                print(f"    INSERT workspace key {key!r} = {value!r}")
            set_config(key, value)
            summary.workspace_inserted += 1
        elif db_val != value:
            # Key present but divergent
            if args.force:
                if args.verbose:
                    print(f"    UPDATE workspace key {key!r}: db={db_val!r} → yaml={value!r}")
                set_config(key, value)
                summary.workspace_updated += 1
            else:
                print(
                    f"  WARNING: workspace key {key!r} divergent:"
                    f" yaml={value!r} db={db_val!r} → skipping (use --force to overwrite)"
                )
                summary.workspace_skipped += 1
        else:
            if args.verbose:
                print(f"    SKIP workspace key {key!r} (already in DB)")


# ---------------------------------------------------------------------------
# Phase 2 — providers.json → llm_providers + active_provider
# ---------------------------------------------------------------------------

def _import_providers(args: argparse.Namespace, summary: _Summary, dry_run: bool) -> None:
    providers_file = CONFIG_DIR / "providers.json"
    if not providers_file.exists():
        # Fall back to example file
        providers_file = CONFIG_DIR / "providers.example.json"
    if not providers_file.exists():
        if args.verbose:
            print("  providers.json not found — skipping providers import")
        return

    try:
        data = json.loads(providers_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ERROR reading providers.json: {exc}")
        return

    providers = data.get("providers", {}) or {}
    active = data.get("active_provider", "anthropic")
    summary.providers_total = len(providers)

    if dry_run:
        print(f"  providers: would import {len(providers)} rows + 1 active_provider")
        return

    from sqlalchemy import text
    from db.engine import get_engine
    from config_store import get_config, set_config

    engine = get_engine()

    for slug, prov in providers.items():
        env_json = json.dumps(prov.get("env_vars", {}))

        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT slug, name, description, cli_command, env_vars, requires_logout"
                     " FROM llm_providers WHERE slug = :s"),
                {"s": slug},
            ).fetchone()

        if existing is None:
            # INSERT
            if args.verbose:
                print(f"    INSERT provider {slug!r}")
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO llm_providers
                            (slug, name, description, cli_command, env_vars, requires_logout)
                        VALUES (:slug, :name, :desc, :cli, :env, :req)
                        ON CONFLICT (slug) DO NOTHING
                    """),
                    {
                        "slug": slug,
                        "name": prov.get("name", slug),
                        "desc": prov.get("description", ""),
                        "cli": prov.get("cli_command", "claude"),
                        "env": env_json,
                        "req": bool(prov.get("requires_logout", False)),
                    },
                )
            summary.providers_inserted += 1
        else:
            # Row exists — check for divergence
            existing_env = {}
            if existing.env_vars:
                try:
                    existing_env = json.loads(existing.env_vars)
                except (json.JSONDecodeError, TypeError):
                    existing_env = {}

            yaml_env = prov.get("env_vars", {}) or {}
            divergent = (
                existing.name != prov.get("name", slug)
                or existing.description != (prov.get("description") or "")
                or existing.cli_command != (prov.get("cli_command", "claude") or "claude")
                or existing_env != yaml_env
            )

            if not divergent:
                if args.verbose:
                    print(f"    SKIP provider {slug!r} (already in DB, same values)")
            elif args.force:
                if args.verbose:
                    print(f"    UPDATE provider {slug!r} (--force)")
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE llm_providers SET
                                name = :name,
                                description = :desc,
                                cli_command = :cli,
                                env_vars = :env,
                                requires_logout = :req,
                                updated_at = NOW()
                            WHERE slug = :slug
                        """),
                        {
                            "slug": slug,
                            "name": prov.get("name", slug),
                            "desc": prov.get("description", ""),
                            "cli": prov.get("cli_command", "claude"),
                            "env": env_json,
                            "req": bool(prov.get("requires_logout", False)),
                        },
                    )
                summary.providers_updated += 1
            else:
                print(
                    f"  WARNING: provider {slug!r} divergent in DB → skipping"
                    " (use --force to overwrite)"
                )
                summary.providers_skipped += 1

    # active_provider in runtime_configs
    db_active = get_config("active_provider")
    if db_active is None:
        if args.verbose:
            print(f"    INSERT active_provider = {active!r}")
        set_config("active_provider", active)
        summary.active_provider_written = True
    elif db_active != active:
        if args.force:
            if args.verbose:
                print(f"    UPDATE active_provider: db={db_active!r} → file={active!r}")
            set_config("active_provider", active)
            summary.active_provider_written = True
        else:
            print(
                f"  WARNING: active_provider divergent:"
                f" file={active!r} db={db_active!r} → skipping (use --force to overwrite)"
            )
    else:
        if args.verbose:
            print(f"    SKIP active_provider (already set to {db_active!r})")


# ---------------------------------------------------------------------------
# Phase 3 — heartbeats.yaml (core) → heartbeats (source_plugin=NULL)
# ---------------------------------------------------------------------------

def _import_heartbeats_core(args: argparse.Namespace, summary: _Summary, dry_run: bool) -> None:
    heartbeats_yaml = CONFIG_DIR / "heartbeats.yaml"
    if not heartbeats_yaml.exists():
        if args.verbose:
            print("  config/heartbeats.yaml not found — skipping core heartbeats import")
        return

    raw = yaml.safe_load(heartbeats_yaml.read_text(encoding="utf-8")) or {}
    hb_list = raw.get("heartbeats", []) or []

    if dry_run:
        print(f"  heartbeats core: would import {len(hb_list)} rows")
        return

    from datetime import datetime, timezone
    from sqlalchemy import text
    from db.engine import get_engine

    engine = get_engine()

    def _now() -> str:
        """Return UTC timestamp in VARCHAR(30)-safe format: YYYY-MM-DDTHH:MM:SS.ffffffZ."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

    written = 0

    with engine.connect() as conn:
        for hb in hb_list:
            hb_id = hb.get("id")
            if not hb_id:
                print(f"  WARNING: heartbeat without 'id' in heartbeats.yaml — skipping")
                continue

            wake_triggers = json.dumps(hb.get("wake_triggers", []) or [])
            required_secrets = json.dumps(hb.get("required_secrets", []) or [])
            agent = hb.get("agent", "")

            # Skip heartbeats that belong to a plugin (merged into core YAML by
            # SQLite-mode loader at runtime). Detected by agent name prefix
            # `plugin-{slug}-` — these are auto-imported via plugin install in PG mode.
            if isinstance(agent, str) and agent.startswith("plugin-"):
                if args.verbose:
                    print(f"    SKIP plugin heartbeat {hb_id!r} (auto-imported via plugin install)")
                continue

            # Core heartbeats: DO NOT rewrite agent name (unlike plugin heartbeats)
            existing = conn.execute(
                text("SELECT id, enabled FROM heartbeats WHERE id = :id AND source_plugin IS NULL"),
                {"id": hb_id},
            ).fetchone()

            now = _now()

            if existing:
                if args.force:
                    # UPDATE — preserve enabled state
                    if args.verbose:
                        print(f"    UPDATE core heartbeat {hb_id!r} (--force, enabled preserved)")
                    conn.execute(
                        text("""
                            UPDATE heartbeats SET
                                agent = :agent,
                                interval_seconds = :ivs,
                                max_turns = :mt,
                                timeout_seconds = :ts,
                                lock_timeout_seconds = :lts,
                                wake_triggers = :wt,
                                goal_id = :gid,
                                required_secrets = :rs,
                                decision_prompt = :dp,
                                updated_at = :uat
                            WHERE id = :id AND source_plugin IS NULL
                        """),
                        {
                            "agent": agent,
                            "ivs": hb.get("interval_seconds", 3600),
                            "mt": hb.get("max_turns", 10),
                            "ts": hb.get("timeout_seconds", 600),
                            "lts": hb.get("lock_timeout_seconds", 1800),
                            "wt": wake_triggers,
                            "gid": hb.get("goal_id"),
                            "rs": required_secrets,
                            "dp": hb.get("decision_prompt", ""),
                            "uat": now,
                            "id": hb_id,
                        },
                    )
                    written += 1
                else:
                    if args.verbose:
                        print(f"    SKIP core heartbeat {hb_id!r} (already in DB)")
            else:
                # INSERT
                if args.verbose:
                    print(f"    INSERT core heartbeat {hb_id!r}")
                conn.execute(
                    text("""
                        INSERT INTO heartbeats
                            (id, agent, interval_seconds, max_turns, timeout_seconds,
                             lock_timeout_seconds, wake_triggers, enabled, goal_id,
                             required_secrets, decision_prompt, source_plugin,
                             created_at, updated_at)
                        VALUES
                            (:id, :agent, :ivs, :mt, :ts, :lts, :wt, :en, :gid,
                             :rs, :dp, NULL, :cat, :uat)
                    """),
                    {
                        "id": hb_id,
                        "agent": agent,
                        "ivs": hb.get("interval_seconds", 3600),
                        "mt": hb.get("max_turns", 10),
                        "ts": hb.get("timeout_seconds", 600),
                        "lts": hb.get("lock_timeout_seconds", 1800),
                        "wt": wake_triggers,
                        "en": bool(hb.get("enabled", False)),
                        "gid": hb.get("goal_id"),
                        "rs": required_secrets,
                        "dp": hb.get("decision_prompt", ""),
                        "cat": now,
                        "uat": now,
                    },
                )
                written += 1

        conn.commit()

    summary.heartbeats_core = written


# ---------------------------------------------------------------------------
# Phase 4 — routines.yaml → routine_definitions (source_plugin=NULL)
# ---------------------------------------------------------------------------

def _import_routines_core(args: argparse.Namespace, summary: _Summary, dry_run: bool) -> None:
    routines_yaml = CONFIG_DIR / "routines.yaml"
    if not routines_yaml.exists():
        if args.verbose:
            print("  config/routines.yaml not found — skipping core routines import")
        return

    raw = yaml.safe_load(routines_yaml.read_text(encoding="utf-8")) or {}
    total = sum(
        len(raw.get(freq, []) or [])
        for freq in ("daily", "weekly", "monthly")
    )

    if dry_run:
        print(f"  routines core: would import {total} rows")
        return

    from routine_store import import_from_yaml

    written = import_from_yaml(routines_yaml, agent_map=None)
    summary.routines_core = written

    if args.verbose:
        print(f"  routines core: {written} rows upserted")


# ---------------------------------------------------------------------------
# Phase 5 — plugins/{slug}/heartbeats.yaml + routines.yaml → tagged source_plugin
# ---------------------------------------------------------------------------

def _import_plugins(args: argparse.Namespace, summary: _Summary, dry_run: bool) -> None:
    if not PLUGINS_DIR.exists():
        return

    # Collect plugin slugs that have at least one importable YAML
    slugs: list[str] = []
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if plugin_dir.name.startswith(".") or not plugin_dir.is_dir():
            continue
        has_hb = (plugin_dir / "heartbeats.yaml").exists()
        has_rt = (plugin_dir / "routines.yaml").exists()
        if has_hb or has_rt:
            slugs.append(plugin_dir.name)

    if not slugs:
        return

    for slug in slugs:
        plugin_dir = PLUGINS_DIR / slug
        hb_file = plugin_dir / "heartbeats.yaml"
        rt_file = plugin_dir / "routines.yaml"

        hb_count = 0
        rt_count = 0

        if hb_file.exists():
            raw = yaml.safe_load(hb_file.read_text(encoding="utf-8")) or {}
            hb_count = len(raw.get("heartbeats", []) or [])

        if rt_file.exists():
            raw_rt = yaml.safe_load(rt_file.read_text(encoding="utf-8")) or {}
            rt_count = sum(
                len(raw_rt.get(f, []) or []) for f in ("daily", "weekly", "monthly")
            )

        if dry_run:
            print(
                f"  plugin {slug}: would import"
                f" {hb_count} heartbeat(s), {rt_count} routine(s)"
            )
            summary.plugins[slug] = {"heartbeats": hb_count, "routines": rt_count}
            continue

        # Import via plugin_loader helpers (already idempotent, PG-only)
        # We need to add backend dir to sys.path for plugin_loader imports
        import sys as _sys
        if str(_BACKEND_DIR) not in _sys.path:
            _sys.path.insert(0, str(_BACKEND_DIR))

        from plugin_loader import (
            _import_plugin_heartbeats_to_db,
            _import_plugin_routines_to_db,
        )

        written_hbs: list[str] = []
        written_rts: list[str] = []

        if hb_file.exists():
            try:
                written_hbs = _import_plugin_heartbeats_to_db(slug)
            except Exception as exc:
                print(f"  WARNING: plugin {slug} heartbeats import failed: {exc}")

        if rt_file.exists():
            try:
                written_rts = _import_plugin_routines_to_db(slug)
            except Exception as exc:
                print(f"  WARNING: plugin {slug} routines import failed: {exc}")

        if args.verbose:
            print(
                f"    plugin {slug}: {len(written_hbs)} heartbeat(s),"
                f" {len(written_rts)} routine(s)"
            )

        summary.plugins[slug] = {
            "heartbeats": len(written_hbs),
            "routines": len(written_rts),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import file-based configs into Postgres. "
            "Use after 'make db-migrate' when configs are still in YAML/JSON files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyse and report what would be imported; write nothing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite DB values that diverge from YAML "
            "(default: skip with warning)."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each individual key/row as it is processed.",
    )
    args = parser.parse_args()

    # Confirm PG mode
    from config_store import get_dialect

    if get_dialect() != "postgresql":
        print("ERROR: This tool only runs against Postgres.")
        print("Set DATABASE_URL=postgresql://... before running.")
        sys.exit(1)

    dry_run: bool = args.dry_run
    summary = _Summary()

    if dry_run:
        print("DRY RUN — no data will be written")
        print()

    print("Phase 1: workspace.yaml → runtime_configs")
    _import_workspace(args, summary, dry_run)

    print("Phase 2: providers.json → llm_providers")
    _import_providers(args, summary, dry_run)

    print("Phase 3: heartbeats.yaml (core) → heartbeats")
    _import_heartbeats_core(args, summary, dry_run)

    print("Phase 4: routines.yaml → routine_definitions")
    _import_routines_core(args, summary, dry_run)

    print("Phase 5: plugins → heartbeats + routine_definitions")
    _import_plugins(args, summary, dry_run)

    print()

    if dry_run:
        # Dry-run report
        plugin_lines = []
        for slug, counts in summary.plugins.items():
            plugin_lines.append(
                f"  plugin {slug}: {counts['heartbeats']} heartbeat(s),"
                f" {counts['routines']} routine(s)"
            )
        plugin_total = sum(
            c["heartbeats"] + c["routines"] for c in summary.plugins.values()
        )

        print("DRY RUN — would import:")
        print(f"  workspace: {summary.workspace_total} keys")
        print(f"  providers: {summary.providers_total} rows + 1 active_provider")
        heartbeat_total_yaml = 0
        hb_yaml = CONFIG_DIR / "heartbeats.yaml"
        if hb_yaml.exists():
            raw = yaml.safe_load(hb_yaml.read_text(encoding="utf-8")) or {}
            heartbeat_total_yaml = len(raw.get("heartbeats", []) or [])
        print(f"  heartbeats core: {heartbeat_total_yaml} rows")
        rt_total_yaml = 0
        rt_yaml = CONFIG_DIR / "routines.yaml"
        if rt_yaml.exists():
            raw_rt = yaml.safe_load(rt_yaml.read_text(encoding="utf-8")) or {}
            rt_total_yaml = sum(len(raw_rt.get(f, []) or []) for f in ("daily", "weekly", "monthly"))
        print(f"  routines core: {rt_total_yaml} rows")
        for line in plugin_lines:
            print(line)
        total_estimated = (
            summary.workspace_total
            + summary.providers_total + 1
            + heartbeat_total_yaml
            + rt_total_yaml
            + plugin_total
        )
        print(f"Total: ~{total_estimated} rows")
    else:
        # Real run report
        plugin_total = sum(
            c["heartbeats"] + c["routines"] for c in summary.plugins.values()
        )
        total = summary.total_rows()

        print(
            f"Import complete."
            f" workspace={summary.workspace_inserted + summary.workspace_updated} keys"
            f" (skipped={summary.workspace_skipped}),"
            f" providers={summary.providers_inserted + summary.providers_updated}"
            f" (skipped={summary.providers_skipped}),"
            f" heartbeats core={summary.heartbeats_core},"
            f" routines core={summary.routines_core},"
            f" plugins={plugin_total}"
        )
        if total == 0:
            print("  (already in DB — import was a no-op)")


if __name__ == "__main__":
    main()
