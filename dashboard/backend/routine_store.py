"""routine_store — DB-native CRUD for routine_definitions (PG mode).

This module is the single source of truth for routine definitions when running
in PostgreSQL mode (ADR pg-native-configs Fase 4).  In SQLite mode the scheduler
and settings endpoints continue to use config/routines.yaml directly.

Import contract
---------------
Both scheduler.py (repo root) and dashboard/backend routes import this module.
scheduler.py adds dashboard/backend to sys.path before importing; routes import
it directly since they already run from dashboard/backend.

Schedule column semantic
------------------------
The ``schedule`` column stores a *human-readable description* for UI display only
(e.g. "daily 06:50", "every 30min", "weekly fri 09:00").  The actual scheduling
decision is made by reading ``config_json``, which preserves the original YAML
shape verbatim ({"time": "06:50"}, {"interval": 30}, {"day": "friday", "time": "09:00"}).
This ensures full compatibility with the current scheduler without inventing cron.

TODO(PG-NC-8): consolidate LISTEN connections via multiplexer if connection
budget becomes issue.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_engine():
    from db.engine import get_engine
    return get_engine()


def _conn():
    return _get_engine().connect()


def _routine_slug(name: str) -> str:
    """Derive a stable slug from a routine name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _build_schedule_label(config_json: dict, frequency: str) -> str:
    """Generate a human-readable schedule description from raw config_json.

    Examples:
      {"time": "06:50"}                    -> "daily 06:50"
      {"interval": 30}                     -> "every 30min"
      {"day": "friday", "time": "09:00"}   -> "weekly fri 09:00"
      {}                                   -> "monthly"
    """
    if frequency == "daily":
        if "interval" in config_json:
            return f"every {config_json['interval']}min"
        return f"daily {config_json.get('time', '')}"
    if frequency == "weekly":
        day = config_json.get("day", config_json.get("days", [""])[0] if config_json.get("days") else "")
        day_short = str(day)[:3].lower()
        return f"weekly {day_short} {config_json.get('time', '')}".strip()
    return "monthly"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_routines(source_plugin: str | None = ...) -> list[dict]:
    """Return all routine_definitions rows as dicts.

    Parameters
    ----------
    source_plugin:
        If omitted (default sentinel), returns all rows.
        If None, returns only core routines (source_plugin IS NULL).
        If a string, returns only routines for that plugin.
    """
    conn = _conn()
    try:
        if source_plugin is ...:
            rows = conn.execute(text("SELECT * FROM routine_definitions ORDER BY id")).fetchall()
        elif source_plugin is None:
            rows = conn.execute(
                text("SELECT * FROM routine_definitions WHERE source_plugin IS NULL ORDER BY id")
            ).fetchall()
        else:
            rows = conn.execute(
                text("SELECT * FROM routine_definitions WHERE source_plugin = :sp ORDER BY id"),
                {"sp": source_plugin},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        conn.close()


def get_routine(routine_id: int) -> dict | None:
    conn = _conn()
    try:
        row = conn.execute(
            text("SELECT * FROM routine_definitions WHERE id = :id"),
            {"id": routine_id},
        ).fetchone()
        return dict(row._mapping) if row else None
    finally:
        conn.close()


def get_routine_by_slug(slug: str, source_plugin: str | None = None) -> dict | None:
    conn = _conn()
    try:
        if source_plugin is None:
            row = conn.execute(
                text("SELECT * FROM routine_definitions WHERE slug = :slug AND source_plugin IS NULL"),
                {"slug": slug},
            ).fetchone()
        else:
            row = conn.execute(
                text("SELECT * FROM routine_definitions WHERE slug = :slug AND source_plugin = :sp"),
                {"slug": slug, "sp": source_plugin},
            ).fetchone()
        return dict(row._mapping) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def upsert_routine(
    slug: str,
    name: str,
    script: str,
    frequency: str,
    config_json: dict,
    agent: str | None = None,
    enabled: bool = False,
    goal_id: int | None = None,
    source_plugin: str | None = None,
) -> int:
    """Insert or update a routine_definitions row.

    Uses ON CONFLICT (slug) WHERE source_plugin IS NULL for core routines,
    or slug + source_plugin for plugin routines.

    Returns the row id.
    """
    schedule_label = _build_schedule_label(config_json, frequency)
    now = _now_iso()

    conn = _conn()
    try:
        # Check if row exists.
        if source_plugin is None:
            existing = conn.execute(
                text("SELECT id FROM routine_definitions WHERE slug = :slug AND source_plugin IS NULL"),
                {"slug": slug},
            ).fetchone()
        else:
            existing = conn.execute(
                text("SELECT id FROM routine_definitions WHERE slug = :slug AND source_plugin = :sp"),
                {"slug": slug, "sp": source_plugin},
            ).fetchone()

        if existing:
            conn.execute(
                text("""
                    UPDATE routine_definitions SET
                        name = :name,
                        script = :script,
                        schedule = :schedule,
                        frequency = :frequency,
                        agent = :agent,
                        goal_id = :goal_id,
                        config_json = :config_json,
                        updated_at = :now
                    WHERE id = :id
                """),
                {
                    "name": name,
                    "script": script,
                    "schedule": schedule_label,
                    "frequency": frequency,
                    "agent": agent,
                    "goal_id": goal_id,
                    "config_json": json.dumps(config_json),
                    "now": now,
                    "id": existing.id,
                },
            )
            conn.commit()
            return existing.id
        else:
            result = conn.execute(
                text("""
                    INSERT INTO routine_definitions
                        (slug, name, script, schedule, frequency, agent,
                         enabled, goal_id, source_plugin, config_json,
                         created_at, updated_at)
                    VALUES
                        (:slug, :name, :script, :schedule, :frequency, :agent,
                         :enabled, :goal_id, :sp, :config_json,
                         :now, :now)
                    RETURNING id
                """),
                {
                    "slug": slug,
                    "name": name,
                    "script": script,
                    "schedule": schedule_label,
                    "frequency": frequency,
                    "agent": agent,
                    "enabled": enabled,
                    "goal_id": goal_id,
                    "sp": source_plugin,
                    "config_json": json.dumps(config_json),
                    "now": now,
                },
            )
            row_id = result.fetchone()[0]
            conn.commit()
            return row_id
    finally:
        conn.close()


def update_routine_fields(routine_id: int, fields: dict[str, Any]) -> bool:
    """Update specific fields of a routine row. Returns True if row was found."""
    allowed = {"enabled", "name", "config_json", "agent", "goal_id", "schedule"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    updates["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)

    conn = _conn()
    try:
        result = conn.execute(
            text(f"UPDATE routine_definitions SET {set_clause} WHERE id = :id"),
            {**updates, "id": routine_id},
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def toggle_routine_enabled(slug: str, source_plugin: str | None = None) -> bool | None:
    """Toggle enabled field. Returns new enabled value, or None if not found."""
    row = get_routine_by_slug(slug, source_plugin)
    if row is None:
        return None
    new_enabled = not row["enabled"]
    update_routine_fields(row["id"], {"enabled": new_enabled})
    return new_enabled


def delete_routine(slug: str, source_plugin: str | None = None) -> bool:
    """Delete a routine by slug. Returns True if deleted."""
    conn = _conn()
    try:
        if source_plugin is None:
            result = conn.execute(
                text("DELETE FROM routine_definitions WHERE slug = :slug AND source_plugin IS NULL"),
                {"slug": slug},
            )
        else:
            result = conn.execute(
                text("DELETE FROM routine_definitions WHERE slug = :slug AND source_plugin = :sp"),
                {"slug": slug, "sp": source_plugin},
            )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# YAML import (startup sync: YAML → DB)
# ---------------------------------------------------------------------------

def import_from_yaml(yaml_path, agent_map: dict | None = None) -> int:
    """Import routines from a routines.yaml file into routine_definitions.

    This is the startup sync for PG mode: called once at boot to ensure
    core routines defined in config/routines.yaml are present in the DB.
    Plugin-owned routines should also call this with source_plugin set.

    Parameters
    ----------
    yaml_path : Path or str
        Path to a routines.yaml file.
    agent_map : dict, optional
        Mapping from script stem → agent slug (from get_script_agents()).

    Returns the number of rows upserted.
    """
    import yaml
    from pathlib import Path

    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        return 0

    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    agents = agent_map or {}
    count = 0

    for frequency in ("daily", "weekly", "monthly"):
        for r in config.get(frequency, []) or []:
            script = r.get("script", "")
            name = r.get("name", script)
            slug = _routine_slug(name)
            script_key = script.replace(".py", "").replace("../", "")
            agent = agents.get(script_key)

            # Build config_json preserving original YAML shape
            cfg: dict = {}
            for field in ("time", "interval", "day", "days", "args"):
                if field in r:
                    cfg[field] = r[field]

            enabled = r.get("enabled", True)
            upsert_routine(
                slug=slug,
                name=name,
                script=script,
                frequency=frequency,
                config_json=cfg,
                agent=agent,
                enabled=enabled,
                goal_id=None,
                source_plugin=None,
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Grouped view (matches settings.py API response shape)
# ---------------------------------------------------------------------------

def list_routines_grouped() -> dict[str, list[dict]]:
    """Return routines grouped by frequency — matches API response shape."""
    rows = list_routines()
    result: dict[str, list] = {"daily": [], "weekly": [], "monthly": []}
    for row in rows:
        freq = row.get("frequency") or "daily"
        cfg = {}
        try:
            cfg = json.loads(row.get("config_json") or "{}")
        except (ValueError, TypeError):
            pass

        entry = {
            "id": row["slug"],
            "slug": row["slug"],
            "name": row["name"],
            "frequency": freq,
            "script": row["script"],
            "args": cfg.get("args", ""),
            "enabled": bool(row["enabled"]),
            "agent": row.get("agent") or "",
            "time": cfg.get("time", ""),
            "interval": cfg.get("interval"),
            "day": cfg.get("day"),
            "days": cfg.get("days"),
        }
        if freq in result:
            result[freq].append(entry)
        else:
            result.setdefault(freq, []).append(entry)

    return result
