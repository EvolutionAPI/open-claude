"""Settings endpoints — workspace.yaml and routines.yaml CRUD."""

import re
import signal
import os
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from routes._helpers import WORKSPACE, get_script_agents
from config_store import get_config, set_config, list_configs, get_dialect

bp = Blueprint("settings", __name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

# Legacy language codes that predate the BCP-47 normalization. setup.py used
# to save "ptBR" without a hyphen; older workspace.yaml files still have it.
# We normalize silently so the dashboard UI (which expects "pt-BR") receives
# a canonical form without forcing users to migrate their .yaml by hand.
#
# Keys are stored in lowercase — lookup in _normalize_language lowercases
# the input first, so "ptBR", "PTBR", "pt_BR", "Pt_Br" all match.
_LANGUAGE_ALIASES = {
    "ptbr": "pt-BR",
    "pt_br": "pt-BR",
    "pt": "pt-BR",
    "enus": "en-US",
    "en_us": "en-US",
    "en": "en-US",
}


def _normalize_language(raw) -> str:
    """Return a canonical BCP-47 tag for legacy / short language codes.

    Safe on empty/None — returns the input unchanged. Unknown codes pass
    through so Portuguese → pt-BR but e.g. "fr" stays "fr" (the UI falls
    back to en-US on unknown codes via the i18n detector).

    Alias lookup is case-insensitive to match the frontend's normalizeLocale
    (which uses /^ptBR$/i etc.), so "PTBR" and "En_Us" resolve correctly too.
    """
    if not raw:
        return raw
    s = str(raw).strip()
    return _LANGUAGE_ALIASES.get(s.lower(), s)


def _load_yaml(path):
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _dump_yaml(path, data):
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)


def _routine_slug(routine: dict) -> str:
    """Derive a stable slug from routine name or script."""
    name = routine.get("name") or routine.get("script", "")
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _require_manage():
    from models import has_permission
    if not has_permission(current_user.role, "config", "manage"):
        abort(403)


# ── Workspace endpoints ───────────────────────────────────────────────────────

@bp.route("/api/settings/workspace")
@login_required
def get_workspace():
    """Return workspace section as JSON.

    In PG mode reads from runtime_configs; in SQLite mode reads workspace.yaml.
    Transparently normalizes legacy language codes ("ptBR" → "pt-BR") in
    the response so the frontend always sees a canonical BCP-47 tag.
    """
    if get_dialect() == "postgresql":
        # Reconstruct nested shape from flat dotted keys.
        flat = list_configs("workspace.")
        workspace: dict = {}
        for dotted_key, val in flat.items():
            # dotted_key is e.g. "workspace.name" — strip leading "workspace."
            leaf = dotted_key[len("workspace."):]
            workspace[leaf] = val
        if "language" in workspace:
            workspace["language"] = _normalize_language(workspace["language"])
        # dashboard section stored under "dashboard.*" keys.
        flat_dash = list_configs("dashboard.")
        dashboard: dict = {}
        for dotted_key, val in flat_dash.items():
            leaf = dotted_key[len("dashboard."):]
            dashboard[leaf] = val
        return jsonify({"workspace": workspace, "dashboard": dashboard})

    # SQLite mode: read YAML directly (unchanged).
    config_path = WORKSPACE / "config" / "workspace.yaml"
    data = _load_yaml(config_path)
    workspace = dict(data.get("workspace") or {})
    if "language" in workspace:
        workspace["language"] = _normalize_language(workspace["language"])
    return jsonify({
        "workspace": workspace,
        "dashboard": data.get("dashboard", {}),
    })


@bp.route("/api/settings/workspace", methods=["PUT"])
@login_required
def update_workspace():
    """Update workspace section fields. Read-merge-write preserves unknown keys."""
    from models import audit
    _require_manage()

    body = request.get_json(force=True) or {}
    actor = getattr(current_user, "id", None)

    if get_dialect() == "postgresql":
        if "workspace" in body:
            allowed_ws = {"name", "owner", "company", "language", "timezone"}
            for k, v in body["workspace"].items():
                if k in allowed_ws:
                    if k == "language":
                        v = _normalize_language(v)
                    set_config(f"workspace.{k}", v, actor_id=actor)
        if "dashboard" in body:
            allowed_dash = {"port"}
            for k, v in body["dashboard"].items():
                if k in allowed_dash:
                    set_config(f"dashboard.{k}", v, actor_id=actor)
        audit(current_user, "workspace_updated", "config", "Updated workspace settings (PG)")
        return jsonify({"status": "saved"})

    # SQLite mode: read-merge-write to workspace.yaml (unchanged).
    config_path = WORKSPACE / "config" / "workspace.yaml"
    data = _load_yaml(config_path)

    if "workspace" in body:
        allowed_ws = {"name", "owner", "company", "language", "timezone"}
        ws = data.setdefault("workspace", {})
        for k, v in body["workspace"].items():
            if k in allowed_ws:
                if k == "language":
                    v = _normalize_language(v)
                ws[k] = v

    if "dashboard" in body:
        allowed_dash = {"port"}
        dash = data.setdefault("dashboard", {})
        for k, v in body["dashboard"].items():
            if k in allowed_dash:
                dash[k] = v

    _dump_yaml(config_path, data)
    audit(current_user, "workspace_updated", "config", "Updated workspace.yaml")
    return jsonify({"status": "saved"})


# ── Routines endpoints ────────────────────────────────────────────────────────

def _routines_path():
    return WORKSPACE / "config" / "routines.yaml"


def _build_routine_entry(r: dict, frequency: str, agents: dict) -> dict:
    """Normalize a raw YAML routine dict into the API response shape."""
    script = r.get("script", "")
    script_key = script.replace(".py", "").replace("../", "")
    agent = agents.get(script_key, "")
    slug = _routine_slug(r)

    entry = {
        "id": slug,
        "slug": slug,
        "name": r.get("name", script),
        "frequency": frequency,
        "script": script,
        "args": r.get("args", ""),
        "enabled": r.get("enabled", True),
        "agent": agent,
        "time": r.get("time", ""),
        "interval": r.get("interval", None),
        "day": r.get("day", None),
        "days": r.get("days", None),
    }
    return entry


@bp.route("/api/settings/routines")
@login_required
def get_routines():
    """Return all routines grouped by frequency.

    PG mode: reads from routine_definitions table via routine_store.
    SQLite mode: reads from config/routines.yaml (unchanged).
    """
    if get_dialect() == "postgresql":
        from routine_store import list_routines_grouped
        return jsonify(list_routines_grouped())

    data = _load_yaml(_routines_path())
    agents = get_script_agents()

    result = {"daily": [], "weekly": [], "monthly": []}
    for freq in ("daily", "weekly", "monthly"):
        for r in data.get(freq, []) or []:
            result[freq].append(_build_routine_entry(r, freq, agents))

    return jsonify(result)


@bp.route("/api/settings/routines/<frequency>/<slug>/toggle", methods=["PATCH"])
@login_required
def toggle_routine(frequency: str, slug: str):
    """Toggle the enabled field of a single routine.

    PG mode: updates routine_definitions via routine_store.
    SQLite mode: updates config/routines.yaml (unchanged).
    """
    from models import audit
    _require_manage()

    if frequency not in ("daily", "weekly", "monthly"):
        abort(400, "Invalid frequency")

    if get_dialect() == "postgresql":
        from routine_store import toggle_routine_enabled
        new_enabled = toggle_routine_enabled(slug)
        if new_enabled is None:
            abort(404, f"Routine '{slug}' not found")
        audit(current_user, "routine_toggled", "config",
              f"Toggled {frequency}/{slug} → enabled={new_enabled} (PG)")
        return jsonify({"status": "ok", "enabled": new_enabled})

    data = _load_yaml(_routines_path())
    routines = data.get(frequency, []) or []

    target = None
    for r in routines:
        if _routine_slug(r) == slug:
            target = r
            break

    if target is None:
        abort(404, f"Routine '{slug}' not found in {frequency}")

    target["enabled"] = not target.get("enabled", True)
    _dump_yaml(_routines_path(), data)
    audit(current_user, "routine_toggled", "config",
          f"Toggled {frequency}/{slug} → enabled={target['enabled']}")
    return jsonify({"status": "ok", "enabled": target["enabled"]})


@bp.route("/api/settings/routines/<frequency>/<slug>", methods=["PUT"])
@login_required
def update_routine(frequency: str, slug: str):
    """Update fields of a single routine.

    PG mode: updates routine_definitions via routine_store.
    SQLite mode: updates config/routines.yaml (unchanged).
    """
    from models import audit
    _require_manage()

    if frequency not in ("daily", "weekly", "monthly"):
        abort(400, "Invalid frequency")

    body = request.get_json(force=True) or {}

    if get_dialect() == "postgresql":
        import json as _json
        from routine_store import get_routine_by_slug, update_routine_fields, _build_schedule_label
        row = get_routine_by_slug(slug)
        if row is None:
            abort(404, f"Routine '{slug}' not found")

        # Merge allowed schedule fields into existing config_json.
        try:
            cfg = _json.loads(row.get("config_json") or "{}")
        except (ValueError, TypeError):
            cfg = {}

        for field in ("time", "interval", "day", "days", "args"):
            if field in body:
                cfg[field] = body[field]

        fields: dict = {"config_json": _json.dumps(cfg)}
        if "enabled" in body:
            fields["enabled"] = body["enabled"]
        if "name" in body:
            fields["name"] = body["name"]
        # Regenerate display label from updated config_json.
        fields["schedule"] = _build_schedule_label(cfg, row.get("frequency") or frequency)

        found = update_routine_fields(row["id"], fields)
        if not found:
            abort(404, f"Routine '{slug}' not found")
        audit(current_user, "routine_updated", "config", f"Updated {frequency}/{slug} (PG)")
        return jsonify({"status": "saved"})

    data = _load_yaml(_routines_path())
    routines = data.get(frequency, []) or []

    target = None
    for r in routines:
        if _routine_slug(r) == slug:
            target = r
            break

    if target is None:
        abort(404, f"Routine '{slug}' not found in {frequency}")

    allowed = {"time", "interval", "day", "days", "args", "enabled", "name"}
    for k, v in body.items():
        if k in allowed:
            target[k] = v

    _dump_yaml(_routines_path(), data)
    audit(current_user, "routine_updated", "config", f"Updated {frequency}/{slug}")
    return jsonify({"status": "saved"})


@bp.route("/api/settings/routines", methods=["POST"])
@login_required
def create_routine():
    """Create a new routine entry.

    PG mode: inserts into routine_definitions via routine_store.
    SQLite mode: appends to config/routines.yaml (unchanged).
    """
    from models import audit
    _require_manage()

    body = request.get_json(force=True) or {}
    frequency = body.get("frequency")
    if frequency not in ("daily", "weekly", "monthly"):
        abort(400, "frequency must be daily, weekly, or monthly")

    required = {"name", "script"}
    missing = required - set(body.keys())
    if missing:
        abort(400, f"Missing required fields: {', '.join(missing)}")

    if get_dialect() == "postgresql":
        from routine_store import upsert_routine, _routine_slug as _rs
        cfg: dict = {}
        for opt in ("time", "interval", "day", "days", "args"):
            if opt in body:
                cfg[opt] = body[opt]
        slug = _rs(body["name"])
        upsert_routine(
            slug=slug,
            name=body["name"],
            script=body["script"],
            frequency=frequency,
            config_json=cfg,
            enabled=body.get("enabled", True),
        )
        audit(current_user, "routine_created", "config",
              f"Created {frequency}/{slug} (PG)")
        return jsonify({"status": "created", "slug": slug}), 201

    entry = {
        "name": body["name"],
        "script": body["script"],
        "enabled": body.get("enabled", True),
    }
    for opt in ("time", "interval", "day", "days", "args"):
        if opt in body:
            entry[opt] = body[opt]

    data = _load_yaml(_routines_path())
    data.setdefault(frequency, [])
    if data[frequency] is None:
        data[frequency] = []
    data[frequency].append(entry)

    _dump_yaml(_routines_path(), data)
    audit(current_user, "routine_created", "config",
          f"Created {frequency}/{_routine_slug(entry)}")
    return jsonify({"status": "created", "slug": _routine_slug(entry)}), 201


@bp.route("/api/settings/routines/<frequency>/<slug>", methods=["DELETE"])
@login_required
def delete_routine(frequency: str, slug: str):
    """Delete a routine by frequency + slug.

    PG mode: deletes from routine_definitions via routine_store.
    SQLite mode: removes from config/routines.yaml (unchanged).
    """
    from models import audit
    _require_manage()

    if frequency not in ("daily", "weekly", "monthly"):
        abort(400, "Invalid frequency")

    if get_dialect() == "postgresql":
        from routine_store import delete_routine as _delete_routine
        deleted = _delete_routine(slug)
        if not deleted:
            abort(404, f"Routine '{slug}' not found")
        audit(current_user, "routine_deleted", "config", f"Deleted {frequency}/{slug} (PG)")
        return jsonify({"status": "deleted"})

    data = _load_yaml(_routines_path())
    routines = data.get(frequency, []) or []

    original_len = len(routines)
    data[frequency] = [r for r in routines if _routine_slug(r) != slug]

    if len(data[frequency]) == original_len:
        abort(404, f"Routine '{slug}' not found in {frequency}")

    _dump_yaml(_routines_path(), data)
    audit(current_user, "routine_deleted", "config", f"Deleted {frequency}/{slug}")
    return jsonify({"status": "deleted"})


# ── Chat settings endpoints ──────────────────────────────────────────────────

@bp.route("/api/settings/chat")
@login_required
def get_chat_settings():
    """Return chat.trustMode setting."""
    if get_dialect() == "postgresql":
        trust_mode = get_config("dashboard.chat.trustMode", False)
        return jsonify({"trustMode": bool(trust_mode)})

    config_path = WORKSPACE / "config" / "workspace.yaml"
    data = _load_yaml(config_path)
    chat = data.get("chat") or {}
    return jsonify({"trustMode": bool(chat.get("trustMode", False))})


@bp.route("/api/settings/chat", methods=["PATCH"])
@login_required
def update_chat_settings():
    """Update chat.trustMode atomically."""
    from models import audit
    _require_manage()

    body = request.get_json(force=True) or {}
    if "trustMode" not in body or not isinstance(body["trustMode"], bool):
        abort(400, "Body must contain trustMode (bool)")

    actor = getattr(current_user, "id", None)

    if get_dialect() == "postgresql":
        set_config("dashboard.chat.trustMode", body["trustMode"], actor_id=actor)
        audit(current_user, "chat_settings_updated", "config",
              f"trustMode set to {body['trustMode']}")
        return jsonify({"trustMode": body["trustMode"]})

    config_path = WORKSPACE / "config" / "workspace.yaml"
    tmp_path = config_path.with_suffix(".yaml.tmp")

    import yaml

    data = _load_yaml(config_path)
    data.setdefault("chat", {})["trustMode"] = body["trustMode"]

    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
    import os as _os
    _os.replace(tmp_path, config_path)

    audit(current_user, "chat_settings_updated", "config",
          f"trustMode set to {body['trustMode']}")
    return jsonify({"trustMode": body["trustMode"]})


# ── Scheduler reload ──────────────────────────────────────────────────────────

@bp.route("/api/settings/scheduler/reload", methods=["POST"])
@login_required
def reload_scheduler():
    """Signal the scheduler to reload routines.yaml.

    Strategy: write a sentinel file that the scheduler watches.
    If scheduler PID is available via .scheduler.pid, also sends SIGHUP.
    """
    from models import audit
    _require_manage()

    sentinel = WORKSPACE / "config" / ".reload"
    try:
        sentinel.touch()
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503

    # Optionally send SIGHUP to scheduler process
    pid_file = WORKSPACE / "ADWs" / "logs" / ".scheduler.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGHUP)
        except Exception:
            pass  # Not fatal — sentinel file is the primary mechanism

    audit(current_user, "scheduler_reloaded", "config", "Sent reload signal to scheduler")
    return jsonify({"status": "reloaded"})


# ── Claude Sessions settings + admin ────────────────────────────────────────
#
# Session resume is opt-in per trigger (Trigger.resume_sessions column).
# These endpoints expose:
#   1) Global defaults — auto-cleanup window, default-on for new triggers
#   2) Sessions admin — list active threads, manual reset for stuck ones
#
# Storage: settings come from config/sessions.yaml (created on first PUT,
# default-empty until then). The trigger_session_threads table is the
# source of truth for active sessions; this UI surface just lets operators
# inspect and reset them without touching the DB directly.

_SESSIONS_CONFIG_PATH = WORKSPACE / "config" / "sessions.yaml"
_SESSIONS_DEFAULTS = {
    "default_resume_for_new_triggers": False,
    "auto_cleanup_days": 7,
    "force_compaction_turns": 50,
    "cleanup_hour_local": 3,  # 03:00 in workspace timezone
}


def _load_sessions_config() -> dict:
    """Load sessions.yaml with defaults filled in for missing keys."""
    cfg = _load_yaml(_SESSIONS_CONFIG_PATH) or {}
    return {**_SESSIONS_DEFAULTS, **cfg}


@bp.route("/api/settings/sessions")
@login_required
def get_sessions_settings():
    """Return Claude Sessions global config + storage stats."""
    _require_manage()
    cfg = _load_sessions_config()

    # Storage stats — best-effort directory size of ~/.claude/projects/
    storage = {"path": "~/.claude/projects/", "session_count": 0, "size_bytes": 0}
    try:
        from pathlib import Path as _P
        proj_dir = _P.home() / ".claude" / "projects"
        if proj_dir.exists():
            count = 0
            total = 0
            for p in proj_dir.rglob("*.jsonl"):
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
            storage["session_count"] = count
            storage["size_bytes"] = total
    except Exception:
        pass

    # Active threads count from DB
    try:
        from models import TriggerSessionThread
        active_threads = TriggerSessionThread.query.count()
    except Exception:
        active_threads = 0

    return jsonify({
        **cfg,
        "storage": storage,
        "active_threads": active_threads,
    })


@bp.route("/api/settings/sessions", methods=["PUT", "PATCH"])
@login_required
def update_sessions_settings():
    """Update Claude Sessions global config."""
    from models import audit
    _require_manage()

    data = request.get_json() or {}
    cfg = _load_sessions_config()

    # Validate + apply
    if "default_resume_for_new_triggers" in data:
        cfg["default_resume_for_new_triggers"] = bool(data["default_resume_for_new_triggers"])
    if "auto_cleanup_days" in data:
        try:
            n = int(data["auto_cleanup_days"])
            if n < 1 or n > 365:
                return jsonify({"error": "auto_cleanup_days must be 1-365"}), 400
            cfg["auto_cleanup_days"] = n
        except (TypeError, ValueError):
            return jsonify({"error": "auto_cleanup_days must be int"}), 400
    if "force_compaction_turns" in data:
        try:
            n = int(data["force_compaction_turns"])
            if n < 1 or n > 500:
                return jsonify({"error": "force_compaction_turns must be 1-500"}), 400
            cfg["force_compaction_turns"] = n
        except (TypeError, ValueError):
            return jsonify({"error": "force_compaction_turns must be int"}), 400
    if "cleanup_hour_local" in data:
        try:
            n = int(data["cleanup_hour_local"])
            if n < 0 or n > 23:
                return jsonify({"error": "cleanup_hour_local must be 0-23"}), 400
            cfg["cleanup_hour_local"] = n
        except (TypeError, ValueError):
            return jsonify({"error": "cleanup_hour_local must be int"}), 400

    # Persist (drop derived keys before save)
    persist = {k: v for k, v in cfg.items() if k in _SESSIONS_DEFAULTS}
    _SESSIONS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _dump_yaml(_SESSIONS_CONFIG_PATH, persist)
    audit(current_user, "update_sessions_settings", "config", str(persist))

    return jsonify({"status": "ok", **persist})


@bp.route("/api/sessions")
@login_required
def list_sessions():
    """List active session threads — for admin UI."""
    _require_manage()
    from models import TriggerSessionThread, Trigger
    from datetime import datetime, timezone

    cfg = _load_sessions_config()
    stale_days = cfg.get("auto_cleanup_days", 7)

    rows = (
        TriggerSessionThread.query
        .order_by(TriggerSessionThread.last_used_at.desc())
        .limit(500)
        .all()
    )
    out = []
    now = datetime.now(timezone.utc)
    for r in rows:
        trig = Trigger.query.get(r.trigger_id)
        last_used = r.last_used_at
        # Normalize to aware datetime for comparison (SQLite returns naive)
        if last_used and last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        age_seconds = int((now - last_used).total_seconds()) if last_used else None
        is_stale = bool(age_seconds is not None and age_seconds > stale_days * 86400)
        out.append({
            **r.to_dict(),
            "trigger_name": trig.name if trig else None,
            "trigger_slug": trig.slug if trig else None,
            "age_seconds": age_seconds,
            "stale": is_stale,
        })
    return jsonify({"sessions": out, "stale_threshold_days": stale_days})


@bp.route("/api/sessions/<int:thread_id>", methods=["DELETE"])
@login_required
def reset_session(thread_id: int):
    """Delete a single session thread row → next webhook starts a fresh
    Claude session for that thread. The underlying ~/.claude/projects/
    JSONL file is NOT deleted (Claude CLI manages those itself); we just
    forget the mapping so we won't pass `--resume` next time.
    """
    from models import audit, db, TriggerSessionThread
    _require_manage()

    row = TriggerSessionThread.query.get_or_404(thread_id)
    trigger_id = row.trigger_id
    dedup_key = row.dedup_key
    db.session.delete(row)
    db.session.commit()
    audit(
        current_user,
        "reset_session",
        "trigger_session_threads",
        f"trigger_id={trigger_id} dedup_key={dedup_key}",
    )
    return jsonify({"status": "reset", "thread_id": thread_id})


@bp.route("/api/sessions/cleanup-stale", methods=["POST"])
@login_required
def cleanup_stale_sessions():
    """Bulk-delete session threads older than auto_cleanup_days."""
    from models import audit, db, TriggerSessionThread
    from datetime import datetime, timedelta, timezone
    _require_manage()

    cfg = _load_sessions_config()
    days = cfg.get("auto_cleanup_days", 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # SQLite stores naive UTC; cast cutoff to naive for cross-dialect filter.
    naive_cutoff = cutoff.replace(tzinfo=None)
    q = TriggerSessionThread.query.filter(
        TriggerSessionThread.last_used_at < naive_cutoff
    )
    count = q.count()
    q.delete(synchronize_session=False)
    db.session.commit()
    audit(
        current_user,
        "cleanup_stale_sessions",
        "trigger_session_threads",
        f"deleted={count} cutoff_days={days}",
    )
    return jsonify({"status": "ok", "deleted": count, "cutoff_days": days})
