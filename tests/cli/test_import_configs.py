"""tests/cli/test_import_configs.py

AC7 — evonexus-import-configs: idempotent, --dry-run, divergence detection, --force.

All tests require a live Postgres instance (DATABASE_URL=postgresql://...).
Marked @pytest.mark.postgres — skipped when Postgres is not configured.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import sqlalchemy as sa
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_BACKEND = _REPO_ROOT / "dashboard" / "backend"
_ALEMBIC_DIR = _REPO_ROOT / "dashboard" / "alembic"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_pg_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _run_alembic_upgrade(db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_ALEMBIC_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"


def _make_args(**kwargs) -> SimpleNamespace:
    """Build a minimal argparse.Namespace for the CLI functions."""
    defaults = {"dry_run": False, "force": False, "verbose": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# YAML fixtures helpers
# ---------------------------------------------------------------------------

def _write_workspace_yaml(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "workspace.yaml").write_text(
        "workspace:\n  name: TestWorkspace\n  owner: Alice\nchat:\n  trustMode: true\n",
        encoding="utf-8",
    )


def _write_providers_json(config_dir: Path) -> None:
    data = {
        "active_provider": "anthropic",
        "providers": {
            "anthropic": {
                "name": "Anthropic",
                "description": "Claude API",
                "cli_command": "claude",
                "env_vars": {"ANTHROPIC_API_KEY": ""},
                "requires_logout": False,
            },
        },
    }
    (config_dir / "providers.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_heartbeats_yaml(config_dir: Path) -> None:
    content = """heartbeats:
- id: test-heartbeat-1
  agent: atlas-project
  interval_seconds: 3600
  max_turns: 5
  timeout_seconds: 300
  lock_timeout_seconds: 1800
  wake_triggers: [interval]
  enabled: false
  goal_id: null
  required_secrets: []
  decision_prompt: "Test prompt"
"""
    (config_dir / "heartbeats.yaml").write_text(content, encoding="utf-8")


def _write_routines_yaml(config_dir: Path) -> None:
    content = """daily:
  - name: "Test Routine"
    script: test_routine.py
    time: "07:00"
    enabled: false
"""
    (config_dir / "routines.yaml").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_engine():
    """Live PG engine with a fresh schema. Skipped if PG is not configured."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not (raw_url.startswith("postgresql") or raw_url.startswith("postgres://")):
        pytest.skip("Postgres not configured (DATABASE_URL not set to PG)")

    url = _norm_pg_url(raw_url)
    try:
        eng = sa.create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")

    _run_alembic_upgrade(raw_url)

    # Wipe config-related tables before each test
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))
        conn.execute(text("DELETE FROM llm_providers"))
        conn.execute(text(
            "DELETE FROM heartbeats WHERE source_plugin IS NULL"
            " AND id LIKE 'test-%'"
        ))
        conn.execute(text(
            "DELETE FROM routine_definitions WHERE source_plugin IS NULL"
            " AND slug = 'test-routine'"
        ))

    yield eng

    # Cleanup after test
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM runtime_configs"))
        conn.execute(text("DELETE FROM llm_providers"))
        conn.execute(text(
            "DELETE FROM heartbeats WHERE source_plugin IS NULL"
            " AND id LIKE 'test-%'"
        ))
        conn.execute(text(
            "DELETE FROM routine_definitions WHERE source_plugin IS NULL"
            " AND slug = 'test-routine'"
        ))
    eng.dispose()


@pytest.fixture
def config_dir(tmp_path: Path):
    """Return a tmp config dir pre-populated with minimal fixture YAMLs."""
    cfg = tmp_path / "config"
    _write_workspace_yaml(cfg)
    _write_providers_json(cfg)
    _write_heartbeats_yaml(cfg)
    _write_routines_yaml(cfg)
    return cfg


def _patch_env(monkeypatch, engine, config_path: Path) -> None:
    """Redirect all store imports to use the test PG engine and config dir."""
    import db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "get_engine", lambda: engine)

    import dashboard.cli.evonexus_import_configs as cli_mod
    monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_path)
    monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_path.parent / "plugins")

    # Reset module-level get_engine references that may be cached
    import importlib
    import config_store
    import provider_store
    import routine_store
    for mod in (config_store, provider_store, routine_store):
        importlib.reload(mod)
    # Reload cli after reloading dependencies
    importlib.reload(cli_mod)
    # Re-patch CONFIG_DIR/PLUGINS_DIR after reload
    monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_path)
    monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_path.parent / "plugins")


# ---------------------------------------------------------------------------
# Test 1 — Idempotence: running twice produces 0 new rows on second run
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestIdempotence:
    def test_run_twice_no_duplicates(self, pg_engine, config_dir, monkeypatch):
        """Second run inserts 0 rows — ON CONFLICT DO NOTHING semantics."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        import dashboard.cli.evonexus_import_configs as cli_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_dir.parent / "plugins")

        from dashboard.cli.evonexus_import_configs import (
            _Summary,
            _import_workspace,
            _import_providers,
            _import_heartbeats_core,
            _import_routines_core,
        )

        args = _make_args()

        # First run
        s1 = _Summary()
        _import_workspace(args, s1, dry_run=False)
        _import_providers(args, s1, dry_run=False)
        _import_heartbeats_core(args, s1, dry_run=False)
        _import_routines_core(args, s1, dry_run=False)

        assert s1.workspace_inserted > 0
        assert s1.providers_inserted > 0
        assert s1.heartbeats_core > 0
        assert s1.routines_core > 0

        # Second run
        s2 = _Summary()
        _import_workspace(args, s2, dry_run=False)
        _import_providers(args, s2, dry_run=False)
        _import_heartbeats_core(args, s2, dry_run=False)
        _import_routines_core(args, s2, dry_run=False)

        # Nothing new inserted
        assert s2.workspace_inserted == 0, "Second run should not insert workspace keys"
        assert s2.workspace_updated == 0, "Second run should not update workspace keys"
        assert s2.providers_inserted == 0, "Second run should not insert providers"
        assert s2.heartbeats_core == 0, "Second run should not insert core heartbeats"
        # routines use upsert — count may differ but DB row count stays same
        with pg_engine.connect() as conn:
            hb_count = conn.execute(
                text("SELECT COUNT(*) FROM heartbeats WHERE source_plugin IS NULL AND id = 'test-heartbeat-1'")
            ).scalar()
            rt_count = conn.execute(
                text("SELECT COUNT(*) FROM routine_definitions WHERE source_plugin IS NULL AND slug = 'test-routine'")
            ).scalar()
        assert hb_count == 1
        assert rt_count == 1


# ---------------------------------------------------------------------------
# Test 2 — Dry-run writes nothing
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestDryRun:
    def test_dry_run_writes_nothing(self, pg_engine, config_dir, monkeypatch):
        """--dry-run: no rows written to any config table."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        import dashboard.cli.evonexus_import_configs as cli_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_dir.parent / "plugins")

        from dashboard.cli.evonexus_import_configs import (
            _Summary,
            _import_workspace,
            _import_providers,
            _import_heartbeats_core,
            _import_routines_core,
        )

        args = _make_args()
        s = _Summary()
        _import_workspace(args, s, dry_run=True)
        _import_providers(args, s, dry_run=True)
        _import_heartbeats_core(args, s, dry_run=True)
        _import_routines_core(args, s, dry_run=True)

        with pg_engine.connect() as conn:
            rc_count = conn.execute(text("SELECT COUNT(*) FROM runtime_configs")).scalar()
            prov_count = conn.execute(text("SELECT COUNT(*) FROM llm_providers")).scalar()
            hb_count = conn.execute(
                text("SELECT COUNT(*) FROM heartbeats WHERE source_plugin IS NULL AND id = 'test-heartbeat-1'")
            ).scalar()
            rt_count = conn.execute(
                text("SELECT COUNT(*) FROM routine_definitions WHERE source_plugin IS NULL AND slug = 'test-routine'")
            ).scalar()

        assert rc_count == 0, "dry-run must not write runtime_configs"
        assert prov_count == 0, "dry-run must not write llm_providers"
        assert hb_count == 0, "dry-run must not write heartbeats"
        assert rt_count == 0, "dry-run must not write routine_definitions"


# ---------------------------------------------------------------------------
# Test 3 — Divergence detection (no --force): warn, skip, no update
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestDivergenceDetection:
    def test_divergence_skips_without_force(self, pg_engine, config_dir, monkeypatch, capsys):
        """After first import, change a DB value — second import (no --force) warns and skips."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        import dashboard.cli.evonexus_import_configs as cli_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_dir.parent / "plugins")

        from dashboard.cli.evonexus_import_configs import (
            _Summary,
            _import_workspace,
        )

        args = _make_args()

        # First run — insert
        s1 = _Summary()
        _import_workspace(args, s1, dry_run=False)
        assert s1.workspace_inserted > 0

        # Manually change workspace.workspace.name in DB
        with pg_engine.begin() as conn:
            conn.execute(
                text("UPDATE runtime_configs SET value = '\"ManuallyEdited\"' WHERE key = 'workspace.workspace.name'")
            )

        # Second run without --force — should warn and skip
        s2 = _Summary()
        _import_workspace(args, s2, dry_run=False)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "workspace.workspace.name" in captured.out
        assert "divergent" in captured.out.lower()
        assert s2.workspace_updated == 0, "Should not update without --force"
        assert s2.workspace_skipped >= 1

        # DB value must remain manually edited
        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM runtime_configs WHERE key = 'workspace.workspace.name'")
            ).fetchone()
        assert row is not None
        import json as _json
        assert _json.loads(row[0]) == "ManuallyEdited"


# ---------------------------------------------------------------------------
# Test 4 — --force overwrites divergent values
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestForceOverwrite:
    def test_force_overwrites_divergent_workspace_key(self, pg_engine, config_dir, monkeypatch):
        """--force: divergent DB value is overwritten with YAML value."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        import dashboard.cli.evonexus_import_configs as cli_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", config_dir.parent / "plugins")

        from dashboard.cli.evonexus_import_configs import (
            _Summary,
            _import_workspace,
        )

        args_no_force = _make_args(force=False)
        args_force = _make_args(force=True)

        # First run
        s1 = _Summary()
        _import_workspace(args_no_force, s1, dry_run=False)

        # Manually change in DB
        with pg_engine.begin() as conn:
            conn.execute(
                text("UPDATE runtime_configs SET value = '\"ManuallyEdited\"' WHERE key = 'workspace.workspace.name'")
            )

        # Run with --force
        s2 = _Summary()
        _import_workspace(args_force, s2, dry_run=False)

        assert s2.workspace_updated >= 1, "--force should update divergent key"

        # DB value must now match YAML
        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM runtime_configs WHERE key = 'workspace.workspace.name'")
            ).fetchone()
        assert row is not None
        import json as _json
        assert _json.loads(row[0]) == "TestWorkspace"


# ---------------------------------------------------------------------------
# Test 5 — Plugin import: heartbeats.yaml in plugins/ → heartbeats with source_plugin
# ---------------------------------------------------------------------------

@pytest.mark.postgres
class TestPluginImport:
    def test_plugin_heartbeat_gets_source_plugin(self, pg_engine, config_dir, monkeypatch, tmp_path):
        """Fixture plugin heartbeats.yaml → heartbeats row with source_plugin='test-plugin'."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        # Create a fake plugin dir with heartbeats.yaml
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "heartbeats.yaml").write_text(
            """heartbeats:
- id: plugin-test-hb-1
  agent: test-agent
  interval_seconds: 7200
  max_turns: 10
  timeout_seconds: 300
  lock_timeout_seconds: 1800
  wake_triggers: [interval]
  enabled: false
  goal_id: null
  required_secrets: []
  decision_prompt: "Plugin test heartbeat"
""",
            encoding="utf-8",
        )

        import dashboard.cli.evonexus_import_configs as cli_mod
        import plugin_loader as pl_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", plugins_dir)
        monkeypatch.setattr(pl_mod, "PLUGINS_DIR", plugins_dir)

        from dashboard.cli.evonexus_import_configs import _Summary, _import_plugins

        args = _make_args()
        s = _Summary()
        _import_plugins(args, s, dry_run=False)

        with pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, source_plugin, agent FROM heartbeats"
                     " WHERE id = 'plugin-test-hb-1'")
            ).fetchone()

        assert row is not None, "Plugin heartbeat row should exist"
        assert row.source_plugin == "test-plugin"
        # Agent name rewritten: bare 'test-agent' → 'plugin-test-plugin-test-agent'
        assert row.agent == "plugin-test-plugin-test-agent"
        assert s.plugins.get("test-plugin", {}).get("heartbeats", 0) == 1

        # Cleanup
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM heartbeats WHERE id = 'plugin-test-hb-1'"))

    def test_plugin_import_idempotent(self, pg_engine, config_dir, monkeypatch, tmp_path):
        """Running plugin import twice does not raise errors or duplicate rows."""
        import db.engine as engine_mod
        monkeypatch.setattr(engine_mod, "get_engine", lambda: pg_engine)

        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "idempotent-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "heartbeats.yaml").write_text(
            """heartbeats:
- id: idempotent-hb-1
  agent: some-agent
  interval_seconds: 3600
  max_turns: 5
  timeout_seconds: 300
  lock_timeout_seconds: 1800
  wake_triggers: [interval]
  enabled: false
  goal_id: null
  required_secrets: []
  decision_prompt: "Idempotent test"
""",
            encoding="utf-8",
        )

        import dashboard.cli.evonexus_import_configs as cli_mod
        import plugin_loader as pl_mod
        monkeypatch.setattr(cli_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cli_mod, "PLUGINS_DIR", plugins_dir)
        monkeypatch.setattr(pl_mod, "PLUGINS_DIR", plugins_dir)

        from dashboard.cli.evonexus_import_configs import _Summary, _import_plugins

        args = _make_args()

        s1 = _Summary()
        _import_plugins(args, s1, dry_run=False)

        s2 = _Summary()
        _import_plugins(args, s2, dry_run=False)

        # Both succeed; DB has exactly 1 row
        with pg_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM heartbeats WHERE id = 'idempotent-hb-1'")
            ).scalar()
        assert count == 1

        # Cleanup
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM heartbeats WHERE id = 'idempotent-hb-1'"))
