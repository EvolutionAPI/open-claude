"""Seed default configs from .example files into DB (PG mode only).

Populates runtime_configs and llm_providers with defaults derived from
config/workspace.example.yaml and config/providers.example.json.

All INSERTs use ON CONFLICT DO NOTHING so the migration is idempotent:
running it twice leaves the DB unchanged after the first run.

SQLite: no-op — defaults come from the *.example.* files at runtime via
        the YAML file backend in config_store.py.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-26

Phase reference: pg-native-configs Fase 7 (setup wizard PG-native)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _workspace_root() -> Path:
    # This file lives at: dashboard/alembic/versions/0010_*.py
    # Workspace root is 3 levels up.
    return Path(__file__).resolve().parents[3]


def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Recursively flatten a nested dict into (dotted_key, json_value) pairs.

    prefix="" means top-level keys become the first segment.
    prefix="foo" means top-level keys become "foo.bar".

    Empty-dict values (e.g. agents: {}) are emitted as a single entry.
    Non-empty dicts are recursed into.
    """
    out: list[tuple[str, str]] = []
    for k, v in d.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            # non-empty nested dict → recurse
            out.extend(_flatten(v, new_key))
        else:
            out.append((new_key, json.dumps(v)))
    return out


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    if not _is_pg():
        return  # SQLite: defaults served from *.example.yaml at runtime.

    conn = op.get_bind()
    root = _workspace_root()

    # -------------------------------------------------------------------------
    # 1. Workspace defaults → runtime_configs
    # -------------------------------------------------------------------------
    ws_example = root / "config" / "workspace.example.yaml"
    if ws_example.exists():
        try:
            import yaml  # available inside alembic env (PyYAML is a core dep)
            data = yaml.safe_load(ws_example.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}

        # workspace.example.yaml already uses namespaced top-level keys
        # (workspace:, dashboard:, chat:) so we flatten with no extra prefix.
        pairs = _flatten(data) if data else []
        for key, value in pairs:
            conn.execute(
                text("""
                    INSERT INTO runtime_configs (key, value)
                    VALUES (:k, :v)
                    ON CONFLICT (key) DO NOTHING
                """),
                {"k": key, "v": value},
            )

    # -------------------------------------------------------------------------
    # 2. Provider defaults → llm_providers + active_provider
    # -------------------------------------------------------------------------
    pr_example = root / "config" / "providers.example.json"
    if pr_example.exists():
        try:
            data = json.loads(pr_example.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        providers = data.get("providers", {})
        for slug, info in providers.items():
            env_vars = info.get("env_vars", {})
            conn.execute(
                text("""
                    INSERT INTO llm_providers
                        (slug, name, description, cli_command, env_vars, requires_logout, enabled)
                    VALUES (:slug, :name, :desc, :cmd, :env, :req, true)
                    ON CONFLICT (slug) DO NOTHING
                """),
                {
                    "slug": slug,
                    "name": info.get("name", slug),
                    "desc": info.get("description", ""),
                    "cmd": info.get("cli_command", "claude"),
                    "env": json.dumps(env_vars),
                    "req": bool(info.get("requires_logout", False)),
                },
            )

        active = data.get("active_provider", "anthropic")
        conn.execute(
            text("""
                INSERT INTO runtime_configs (key, value)
                VALUES ('active_provider', :v)
                ON CONFLICT (key) DO NOTHING
            """),
            {"v": json.dumps(active)},
        )


def downgrade() -> None:
    if not _is_pg():
        return

    conn = op.get_bind()

    # Remove only the rows this migration inserted.
    # Keys inserted: workspace.* hierarchy + active_provider.
    conn.execute(
        text("""
            DELETE FROM runtime_configs
            WHERE key LIKE 'workspace.%' OR key = 'active_provider'
        """)
    )

    # Remove provider rows seeded from the example file only (no user edits at
    # this point in a fresh install).  In a non-fresh DB the DBA should review
    # before running downgrade.
    root = _workspace_root()
    pr_example = root / "config" / "providers.example.json"
    if pr_example.exists():
        try:
            data = json.loads(pr_example.read_text(encoding="utf-8"))
            slugs = list(data.get("providers", {}).keys())
        except Exception:
            slugs = []
        for slug in slugs:
            conn.execute(
                text("DELETE FROM llm_providers WHERE slug = :s"),
                {"s": slug},
            )
