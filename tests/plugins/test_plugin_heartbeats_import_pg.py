"""PG-mode plugin contract — auto-import of heartbeats and routines on install/update/uninstall.

ADR: pg-native-configs Fase 5
AC4: Install in PG populates heartbeats table with source_plugin=<slug>, enabled=False.
AC5: Uninstall deletes only rows with source_plugin=<slug>; user rows survive.
     Audit payload includes deleted IDs.

Scenarios covered
-----------------
install:
  - heartbeats.yaml present  → rows inserted with source_plugin, enabled=False, agent rewritten
  - heartbeats.yaml absent   → no-op, no error
  - routines.yaml present    → routine_definitions rows inserted with source_plugin
  - routines.yaml absent     → no-op

uninstall:
  - plugin rows deleted; user row (source_plugin IS NULL) survives
  - deleted IDs returned by helper (for audit)
  - routines: same pattern

update (enabled-preservation):
  - user-modified enabled=True survives plugin update
  - new heartbeat added by update gets enabled=False
  - existing enabled=False stays False

SQLite:
  - all helpers are no-ops; return empty lists
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin_dir(tmp_path: Path, slug: str, heartbeats: list | None, routines: dict | None) -> Path:
    """Create a minimal plugin directory with optional YAML files."""
    plugin_dir = tmp_path / slug
    plugin_dir.mkdir(parents=True)
    if heartbeats is not None:
        import yaml
        (plugin_dir / "heartbeats.yaml").write_text(
            yaml.dump({"heartbeats": heartbeats}), encoding="utf-8"
        )
    if routines is not None:
        import yaml
        (plugin_dir / "routines.yaml").write_text(
            yaml.dump(routines), encoding="utf-8"
        )
    return plugin_dir


def _patch_dialect(dialect_name: str):
    """Patch get_engine().dialect.name seen by plugin_loader._get_dialect_name()."""
    fake_dialect = MagicMock()
    fake_dialect.name = dialect_name
    fake_engine = MagicMock()
    fake_engine.dialect = fake_dialect
    return patch("plugin_loader._get_dialect_name", return_value=dialect_name)


def _patch_plugins_dir(new_dir: Path):
    """Patch plugin_loader.PLUGINS_DIR so helpers look in tmp_path."""
    return patch("plugin_loader.PLUGINS_DIR", new_dir)


def _make_in_memory_engine():
    """Return a SQLAlchemy in-memory SQLite engine with the heartbeats/routine_definitions tables."""
    from sqlalchemy import create_engine, text as sa_text
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS heartbeats (
                id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 3600,
                max_turns INTEGER NOT NULL DEFAULT 10,
                timeout_seconds INTEGER NOT NULL DEFAULT 600,
                lock_timeout_seconds INTEGER NOT NULL DEFAULT 1800,
                wake_triggers TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 0,
                goal_id TEXT,
                required_secrets TEXT DEFAULT '[]',
                decision_prompt TEXT NOT NULL DEFAULT '',
                source_plugin TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """))
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS routine_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL DEFAULT '',
                script TEXT NOT NULL DEFAULT '',
                agent TEXT,
                frequency TEXT NOT NULL DEFAULT 'daily',
                enabled INTEGER NOT NULL DEFAULT 1,
                goal_id INTEGER,
                source_plugin TEXT,
                config_json TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            )
        """))
        conn.commit()
    return engine


def _patch_db_engine(engine):
    """Patch db.engine.get_engine() so helpers use the given in-memory engine."""
    return patch("plugin_loader._get_db", return_value=engine.connect())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with required tables."""
    return _make_in_memory_engine()


@pytest.fixture()
def plugin_slug():
    return "evo-essentials"


@pytest.fixture()
def hb_list():
    """Two heartbeat definitions as they appear in heartbeats.yaml."""
    return [
        {
            "id": "evo-essentials-hb-1",
            "agent": "atlas",
            "interval_seconds": 3600,
            "max_turns": 10,
            "timeout_seconds": 300,
            "lock_timeout_seconds": 1800,
            "wake_triggers": ["interval", "manual"],
            "goal_id": None,
            "required_secrets": [],
            "decision_prompt": "Check project status.",
        },
        {
            "id": "evo-essentials-hb-2",
            "agent": "zara",
            "interval_seconds": 7200,
            "decision_prompt": "Check support queue.",
        },
    ]


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

from plugin_loader import (  # noqa: E402
    _import_plugin_heartbeats_to_db_impl,
    _delete_plugin_heartbeats_from_db,
    _import_plugin_routines_to_db_impl,
    _delete_plugin_routines_from_db,
    _reimport_plugin_configs_preserving_enabled,
)


# ---------------------------------------------------------------------------
# SQLite no-op tests (dialect gate)
# ---------------------------------------------------------------------------

class TestSQLiteNoOp:
    """All helpers must be no-ops in SQLite mode."""

    def test_import_heartbeats_sqlite_noop(self, tmp_path, plugin_slug, hb_list):
        plugin_dir = _make_plugin_dir(tmp_path, plugin_slug, hb_list, None)
        with _patch_dialect("sqlite"), _patch_plugins_dir(tmp_path):
            result = _import_plugin_heartbeats_to_db_impl(plugin_slug)
        assert result == []

    def test_delete_heartbeats_sqlite_noop(self, plugin_slug):
        with _patch_dialect("sqlite"):
            result = _delete_plugin_heartbeats_from_db(plugin_slug)
        assert result == []

    def test_import_routines_sqlite_noop(self, tmp_path, plugin_slug):
        _make_plugin_dir(tmp_path, plugin_slug, None, {"daily": [{"name": "r1", "script": "r1.py"}]})
        with _patch_dialect("sqlite"), _patch_plugins_dir(tmp_path):
            result = _import_plugin_routines_to_db_impl(plugin_slug)
        assert result == []

    def test_delete_routines_sqlite_noop(self, plugin_slug):
        with _patch_dialect("sqlite"):
            result = _delete_plugin_routines_from_db(plugin_slug)
        assert result == []

    def test_reimport_sqlite_noop(self, plugin_slug):
        with _patch_dialect("sqlite"):
            result = _reimport_plugin_configs_preserving_enabled(plugin_slug)
        assert result == {"heartbeats": [], "routines": []}


# ---------------------------------------------------------------------------
# Install path — heartbeats
# ---------------------------------------------------------------------------

class TestInstallHeartbeats:
    """AC4: Install in PG inserts heartbeat rows with correct field values."""

    def _run_import(self, tmp_path, plugin_slug, hb_list, engine):
        plugin_dir = _make_plugin_dir(tmp_path, plugin_slug, hb_list, None)
        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: engine.connect()),
        ):
            return _import_plugin_heartbeats_to_db_impl(plugin_slug)

    def test_returns_inserted_ids(self, tmp_path, plugin_slug, hb_list, mem_engine):
        result = self._run_import(tmp_path, plugin_slug, hb_list, mem_engine)
        assert set(result) == {"evo-essentials-hb-1", "evo-essentials-hb-2"}

    def test_rows_have_source_plugin(self, tmp_path, plugin_slug, hb_list, mem_engine):
        self._run_import(tmp_path, plugin_slug, hb_list, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(
                sa_text("SELECT id, source_plugin FROM heartbeats WHERE source_plugin = :sp"),
                {"sp": plugin_slug},
            ).fetchall()
        assert len(rows) == 2
        assert all(r[1] == plugin_slug for r in rows)

    def test_enabled_false_by_default(self, tmp_path, plugin_slug, hb_list, mem_engine):
        self._run_import(tmp_path, plugin_slug, hb_list, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(sa_text("SELECT enabled FROM heartbeats")).fetchall()
        assert all(bool(r[0]) is False for r in rows)

    def test_agent_rewrite(self, tmp_path, plugin_slug, hb_list, mem_engine):
        """bare agent name must be prefixed with plugin-{slug}-"""
        self._run_import(tmp_path, plugin_slug, hb_list, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(sa_text("SELECT id, agent FROM heartbeats")).fetchall()
        by_id = {r[0]: r[1] for r in rows}
        assert by_id["evo-essentials-hb-1"] == "plugin-evo-essentials-atlas"
        assert by_id["evo-essentials-hb-2"] == "plugin-evo-essentials-zara"

    def test_already_prefixed_agent_unchanged(self, tmp_path, plugin_slug, mem_engine):
        """Agent already prefixed with plugin-{slug}- must not be double-prefixed."""
        hb = [{"id": "hb-pre", "agent": "plugin-evo-essentials-atlas", "interval_seconds": 100, "decision_prompt": "x"}]
        self._run_import(tmp_path, plugin_slug, hb, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            row = conn.execute(sa_text("SELECT agent FROM heartbeats WHERE id='hb-pre'")).fetchone()
        assert row[0] == "plugin-evo-essentials-atlas"

    def test_system_agent_unchanged(self, tmp_path, plugin_slug, mem_engine):
        hb = [{"id": "hb-sys", "agent": "system", "interval_seconds": 100, "decision_prompt": "x"}]
        self._run_import(tmp_path, plugin_slug, hb, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            row = conn.execute(sa_text("SELECT agent FROM heartbeats WHERE id='hb-sys'")).fetchone()
        assert row[0] == "system"

    def test_missing_yaml_is_noop(self, tmp_path, plugin_slug, mem_engine):
        """No heartbeats.yaml → returns [] without error."""
        plugin_dir = tmp_path / plugin_slug
        plugin_dir.mkdir(parents=True, exist_ok=True)
        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            result = _import_plugin_heartbeats_to_db_impl(plugin_slug)
        assert result == []


# ---------------------------------------------------------------------------
# Uninstall path — heartbeats
# ---------------------------------------------------------------------------

class TestUninstallHeartbeats:
    """AC5: Uninstall deletes only plugin rows; user row survives."""

    def _seed_rows(self, engine, plugin_slug: str):
        """Insert 2 plugin rows and 1 user row."""
        from sqlalchemy import text as sa_text
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with engine.connect() as conn:
            for hb_id, sp in [
                ("evo-essentials-hb-1", plugin_slug),
                ("evo-essentials-hb-2", plugin_slug),
                ("user-heartbeat-1", None),
            ]:
                conn.execute(sa_text("""
                    INSERT INTO heartbeats (id, agent, interval_seconds, decision_prompt, source_plugin, created_at, updated_at)
                    VALUES (:id, 'some-agent', 3600, 'check stuff', :sp, :now, :now)
                """), {"id": hb_id, "sp": sp, "now": now})
            conn.commit()

    def test_deletes_plugin_rows(self, plugin_slug, mem_engine):
        self._seed_rows(mem_engine, plugin_slug)
        with (
            _patch_dialect("postgresql"),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            deleted = _delete_plugin_heartbeats_from_db(plugin_slug)
        assert set(deleted) == {"evo-essentials-hb-1", "evo-essentials-hb-2"}

    def test_user_row_survives(self, plugin_slug, mem_engine):
        self._seed_rows(mem_engine, plugin_slug)
        with (
            _patch_dialect("postgresql"),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            _delete_plugin_heartbeats_from_db(plugin_slug)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(sa_text("SELECT id FROM heartbeats")).fetchall()
        assert [r[0] for r in rows] == ["user-heartbeat-1"]

    def test_returns_empty_when_no_rows(self, plugin_slug, mem_engine):
        with (
            _patch_dialect("postgresql"),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            deleted = _delete_plugin_heartbeats_from_db(plugin_slug)
        assert deleted == []


# ---------------------------------------------------------------------------
# Install path — routines
# ---------------------------------------------------------------------------

class TestInstallRoutines:
    """Routines are imported into routine_definitions with source_plugin tag."""

    _routines_yaml = {
        "daily": [
            {"name": "daily-report", "script": "daily_report.py", "time": "06:50"},
        ],
        "weekly": [
            {"name": "weekly-review", "script": "weekly_review.py", "day": "friday", "time": "09:00"},
        ],
    }

    def _run_import(self, tmp_path, plugin_slug, engine):
        _make_plugin_dir(tmp_path, plugin_slug, None, self._routines_yaml)
        # routine_store.upsert_routine uses its own _get_engine(); patch it too.
        import routine_store as _rs
        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: engine.connect()),
            patch.object(_rs, "_get_engine", return_value=engine),
        ):
            return _import_plugin_routines_to_db_impl(plugin_slug)

    def test_returns_routine_slugs(self, tmp_path, plugin_slug, mem_engine):
        result = self._run_import(tmp_path, plugin_slug, mem_engine)
        assert set(result) == {"daily-report", "weekly-review"}

    def test_rows_have_source_plugin(self, tmp_path, plugin_slug, mem_engine):
        self._run_import(tmp_path, plugin_slug, mem_engine)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(
                sa_text("SELECT slug, source_plugin FROM routine_definitions"),
            ).fetchall()
        assert len(rows) == 2
        assert all(r[1] == plugin_slug for r in rows)


# ---------------------------------------------------------------------------
# Uninstall path — routines
# ---------------------------------------------------------------------------

class TestUninstallRoutines:
    def _seed_rows(self, engine, plugin_slug: str):
        from sqlalchemy import text as sa_text
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with engine.connect() as conn:
            for slug, sp in [
                ("daily-report", plugin_slug),
                ("weekly-review", plugin_slug),
                ("user-routine", None),
            ]:
                conn.execute(sa_text("""
                    INSERT INTO routine_definitions
                        (slug, name, schedule, script, frequency, enabled, source_plugin, config_json, created_at, updated_at)
                    VALUES (:slug, :slug, '', 'x.py', 'daily', 1, :sp, '{}', :now, :now)
                """), {"slug": slug, "sp": sp, "now": now})
            conn.commit()

    def test_deletes_plugin_rows(self, plugin_slug, mem_engine):
        self._seed_rows(mem_engine, plugin_slug)
        with (
            _patch_dialect("postgresql"),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            deleted = _delete_plugin_routines_from_db(plugin_slug)
        assert set(deleted) == {"daily-report", "weekly-review"}

    def test_user_row_survives(self, plugin_slug, mem_engine):
        self._seed_rows(mem_engine, plugin_slug)
        with (
            _patch_dialect("postgresql"),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            _delete_plugin_routines_from_db(plugin_slug)
        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(sa_text("SELECT slug FROM routine_definitions")).fetchall()
        assert [r[0] for r in rows] == ["user-routine"]


# ---------------------------------------------------------------------------
# Update path — enabled preservation
# ---------------------------------------------------------------------------

class TestUpdateEnabledPreservation:
    """Plugin update must not reset user-modified enabled flags (PRD Q9)."""

    _hb_list_v1 = [
        {"id": "hb-a", "agent": "atlas", "interval_seconds": 3600, "decision_prompt": "check"},
        {"id": "hb-b", "agent": "zara", "interval_seconds": 7200, "decision_prompt": "check"},
    ]
    _hb_list_v2 = [
        {"id": "hb-a", "agent": "atlas", "interval_seconds": 1800, "decision_prompt": "check v2"},
        {"id": "hb-b", "agent": "zara", "interval_seconds": 7200, "decision_prompt": "check"},
        {"id": "hb-c", "agent": "flux", "interval_seconds": 14400, "decision_prompt": "new heartbeat"},
    ]

    def _install_v1_with_enabled(self, tmp_path, plugin_slug, mem_engine, enabled_map: dict[str, bool]):
        """Seed DB with v1 heartbeats, then manually set enabled flags."""
        from sqlalchemy import text as sa_text
        _make_plugin_dir(tmp_path, plugin_slug, self._hb_list_v1, None)
        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            _import_plugin_heartbeats_to_db_impl(plugin_slug)
        # Simulate user enabling some heartbeats
        with mem_engine.connect() as conn:
            for hb_id, en in enabled_map.items():
                conn.execute(
                    sa_text("UPDATE heartbeats SET enabled = :en WHERE id = :id"),
                    {"en": 1 if en else 0, "id": hb_id},
                )
            conn.commit()

    def test_enabled_survives_update(self, tmp_path, plugin_slug, mem_engine):
        """hb-a was enabled by user → must remain enabled after update."""
        self._install_v1_with_enabled(tmp_path, plugin_slug, mem_engine, {"hb-a": True, "hb-b": False})

        # Simulate update: replace plugin dir with v2 content
        import shutil
        shutil.rmtree(tmp_path / plugin_slug)
        _make_plugin_dir(tmp_path, plugin_slug, self._hb_list_v2, None)

        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            result = _reimport_plugin_configs_preserving_enabled(plugin_slug)

        assert set(result["heartbeats"]) == {"hb-a", "hb-b", "hb-c"}

        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            rows = conn.execute(
                sa_text("SELECT id, enabled FROM heartbeats WHERE source_plugin = :sp"),
                {"sp": plugin_slug},
            ).fetchall()
        by_id = {r[0]: bool(r[1]) for r in rows}

        # hb-a: user set enabled=True → must survive
        assert by_id["hb-a"] is True, "user-enabled hb-a must survive update"
        # hb-b: user left disabled → stays False
        assert by_id["hb-b"] is False
        # hb-c: new in v2 → enabled=False by default
        assert by_id["hb-c"] is False, "new heartbeat added by update must default to enabled=False"

    def test_update_applies_new_field_values(self, tmp_path, plugin_slug, mem_engine):
        """interval_seconds update from 3600→1800 must be applied even when enabled preserved."""
        self._install_v1_with_enabled(tmp_path, plugin_slug, mem_engine, {"hb-a": True})

        import shutil
        shutil.rmtree(tmp_path / plugin_slug)
        _make_plugin_dir(tmp_path, plugin_slug, self._hb_list_v2, None)

        with (
            _patch_dialect("postgresql"),
            _patch_plugins_dir(tmp_path),
            patch("plugin_loader._get_db", side_effect=lambda: mem_engine.connect()),
        ):
            _reimport_plugin_configs_preserving_enabled(plugin_slug)

        from sqlalchemy import text as sa_text
        with mem_engine.connect() as conn:
            row = conn.execute(
                sa_text("SELECT interval_seconds FROM heartbeats WHERE id = 'hb-a'")
            ).fetchone()
        assert row[0] == 1800, "updated interval_seconds must be written even when enabled is preserved"
