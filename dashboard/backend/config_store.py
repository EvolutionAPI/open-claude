"""
config_store — dialect-bifurcated config read/write helper.

PostgreSQL: configs live in runtime_configs / llm_providers / routine_definitions.
SQLite:     configs stay in config/*.yaml and config/*.json (unchanged from v0.33.x).

This is the ONLY authorised seam for reading and writing EvoNexus configs.
Call sites must not do `if dialect == ...` directly — delegate here.

Public API (Phase 1 — workspace + providers key/value only):
    get_config(key, default=None)  -> Any
    set_config(key, value, actor_id=None)  -> None
    list_configs(prefix="")        -> dict[str, Any]

Phase 3 (heartbeats) and Phase 4 (routines) will extend this module.
Phase 5 (plugin contract) will add load_heartbeats/save_heartbeats.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Dialect detection — no circular import: engine module only reads os.environ.
# ---------------------------------------------------------------------------
from db.engine import get_engine

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = WORKSPACE_ROOT / "config"


def get_dialect() -> str:
    """Return the active SQLAlchemy dialect name ('postgresql' or 'sqlite')."""
    return get_engine().dialect.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_config(key: str, default: Any = None) -> Any:
    """Return a config value by namespaced key.

    Examples:
        get_config('workspace.name')
        get_config('active_provider', 'anthropic')
    """
    if get_dialect() == "postgresql":
        return _get_from_db(key, default)
    return _get_from_yaml(key, default)


def set_config(key: str, value: Any, actor_id: Optional[int] = None) -> None:
    """Write a config value by namespaced key.

    In PG mode performs an UPSERT into runtime_configs.
    In SQLite mode performs an atomic YAML rewrite.
    """
    if get_dialect() == "postgresql":
        _set_in_db(key, value, actor_id)
    else:
        _set_in_yaml(key, value)


def list_configs(prefix: str = "") -> dict:
    """Return a flat dict of all config keys (optionally filtered by prefix).

    Example:
        list_configs('workspace.')  # -> {'workspace.name': '...', ...}
    """
    if get_dialect() == "postgresql":
        return _list_from_db(prefix)
    return _list_from_yaml(prefix)


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------

def _get_from_db(key: str, default: Any) -> Any:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT value FROM runtime_configs WHERE key = :k"),
            {"k": key},
        ).fetchone()
        if row is None:
            return default
        return json.loads(row.value)


def _set_in_db(key: str, value: Any, actor_id: Optional[int]) -> None:
    serialized = json.dumps(value)
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO runtime_configs (key, value, updated_by, version)
                VALUES (:k, :v, :a, 1)
                ON CONFLICT (key) DO UPDATE
                    SET value      = EXCLUDED.value,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW(),
                        version    = runtime_configs.version + 1
            """),
            {"k": key, "v": serialized, "a": actor_id},
        )


def _list_from_db(prefix: str) -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT key, value FROM runtime_configs WHERE key LIKE :p"),
            {"p": f"{prefix}%"},
        ).fetchall()
        return {r.key: json.loads(r.value) for r in rows}


# ---------------------------------------------------------------------------
# SQLite (YAML file) backend
# ---------------------------------------------------------------------------

def _get_from_yaml(key: str, default: Any) -> Any:
    """Resolve a dotted key by mapping the first segment to a YAML filename.

    Example: 'workspace.name' → config/workspace.yaml → data['workspace']['name']
    """
    parts = key.split(".")
    file_root = parts[0]
    yaml_path = CONFIG_DIR / f"{file_root}.yaml"
    if not yaml_path.exists():
        return default
    data = yaml.safe_load(yaml_path.read_text()) or {}
    cur = data
    for p in parts[1:]:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _set_in_yaml(key: str, value: Any) -> None:
    """Atomic YAML write via tmp-file rename."""
    parts = key.split(".")
    file_root = parts[0]
    yaml_path = CONFIG_DIR / f"{file_root}.yaml"
    data = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}
    if data is None:
        data = {}
    cur = data
    for p in parts[1:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    # Ensure parent directory exists (config/ should already exist in practice).
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = yaml_path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    tmp.replace(yaml_path)


def _list_from_yaml(prefix: str) -> dict:
    """Flatten all non-example YAML files into a dotted-key dict."""
    result: dict = {}
    if not CONFIG_DIR.exists():
        return result
    for yaml_file in CONFIG_DIR.glob("*.yaml"):
        if yaml_file.name.endswith(".example.yaml"):
            continue
        data = yaml.safe_load(yaml_file.read_text()) or {}
        root = yaml_file.stem
        for k, v in _flatten(data, root):
            if k.startswith(prefix):
                result[k] = v
    return result


def _flatten(d: dict, parent: str) -> list:
    """Recursively flatten a nested dict into (dotted_key, value) pairs."""
    out = []
    for k, v in d.items():
        new_key = f"{parent}.{k}"
        if isinstance(v, dict):
            out.extend(_flatten(v, new_key))
        else:
            out.append((new_key, v))
    return out
