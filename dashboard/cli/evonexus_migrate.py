"""evonexus-migrate — SQLite → PostgreSQL data migration tool.

Usage
-----
    python -m dashboard.cli.evonexus_migrate \\
        --source sqlite:////path/to/dashboard.db \\
        --target 'postgresql://user:pass@host/db' \\
        [--dry-run] [--resume] [--allow-non-empty] \\
        [--batch-size 1000] [--skip-verify] [--verbose]

Pre-requisites
--------------
1. Target Postgres schema must already exist via ``alembic upgrade head``.
2. Source SQLite is read-only during migration (tool never modifies origin).
3. Target is preferably empty; use ``--allow-non-empty`` to migrate into a
   populated target (idempotent — ON CONFLICT DO NOTHING on all inserts).

Trigger discipline (ADR PG-Q3 F6 corollary)
--------------------------------------------
Before bulk-copying ``goal_tasks`` the Postgres trigger
``trg_task_done_updates_goal`` is DISABLED so that migrating rows already in
status='done' does not double-increment ``goals.current_value``.  After the
copy the trigger is re-enabled and a drift-correction pass reconciles any
goal whose ``current_value`` diverges from ``goal_progress_v.derived_value``.

Idempotency
-----------
All inserts use ``INSERT ... ON CONFLICT DO NOTHING`` so re-running on a
populated target is a no-op.  With ``--resume`` an ``evonexus_migration_state``
table on the target records which tables completed; interrupted runs restart
from the first incomplete table.

Verification (``--verify``, default ON)
----------------------------------------
After migration the tool counts rows in both backends per table and computes
a canonical checksum (sorted primary-key hash).  Any diff → non-zero exit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Table definitions — order respects FK dependencies
# ---------------------------------------------------------------------------

# Boolean columns that arrive as INTEGER 0/1 from SQLite and must be cast to
# Python bool before inserting into Postgres (ADR PG-Q5).
_BOOL_COLUMNS: dict[str, set[str]] = {
    "users":              {"is_active", "onboarding_completed_agents_visit"},
    "triggers":           {"enabled"},
    "systems":            {"enabled"},
    "heartbeats":         {"enabled"},
    "brain_repo_configs": {"sync_enabled", "sync_in_progress", "cancel_requested"},
    "plugin_scan_cache":  {"llm_augmented"},
    "plugins_installed":  {"enabled"},
}

# Datetime/timestamp columns stored as ISO-8601 TEXT in SQLite; must be
# parsed into datetime objects when targeting Postgres (ADR PG-Q2).
_DATETIME_COLUMNS: dict[str, set[str]] = {
    "users":                        {"created_at", "last_login"},
    "audit_log":                    {"created_at"},
    "login_throttles":              {"locked_until", "last_attempt_at"},
    "scheduled_tasks":              {"created_at", "updated_at"},
    "triggers":                     {"created_at", "updated_at"},
    "trigger_executions":           {"started_at", "ended_at"},
    "runtime_configs":              {"updated_at"},
    "systems":                      {"created_at"},
    "file_shares":                  {"created_at", "expires_at"},
    "brain_repo_configs":           {"last_sync", "sync_started_at", "created_at", "updated_at"},
    "plugin_scan_cache":            {"created_at"},
    "plugin_audit_log":             {"created_at"},
    "knowledge_connections":        {"last_health_check", "created_at"},
    "knowledge_connection_events":  {"created_at"},
}

# Tables whose PK is a SERIAL/INTEGER on Postgres — sequence must be reset
# after bulk insert with preserved IDs so future INSERTs don't collide.
_INTEGER_PK_TABLES: list[tuple[str, str]] = [
    ("users",                       "id"),
    ("roles",                       "id"),
    ("audit_log",                   "id"),
    ("login_throttles",             "id"),
    ("scheduled_tasks",             "id"),
    ("triggers",                    "id"),
    ("trigger_executions",          "id"),
    ("runtime_configs",             "id"),
    ("systems",                     "id"),
    ("file_shares",                 "id"),
    ("missions",                    "id"),
    ("projects",                    "id"),
    ("goals",                       "id"),
    ("goal_tasks",                  "id"),
    ("brain_repo_configs",          "id"),
    ("plugin_scan_cache",           "id"),
    ("plugin_audit_log",            "id"),
    ("knowledge_connection_events", "id"),
]

# Tables with a non-standard single PK column name (not 'id').
# Confirmed from 0002_core_schema.py:
#   heartbeat_runs  → run_id  (String, primary_key)
#   heartbeats      → id      (String — already 'id', no override needed)
_NONSTANDARD_PK: dict[str, str] = {
    "heartbeat_runs": "run_id",
}

# Tables that have composite PKs (no single ``id`` column) — idempotency
# uses ON CONFLICT DO NOTHING without specifying a column list.
_COMPOSITE_PK_TABLES: set[str] = {
    "plugin_hook_circuit_state",
    "integration_health_cache",
}

# Ordered migration sequence — FK parents before FK children.
TABLES_IN_ORDER: list[str] = [
    # ---------- core / independent ----------
    "users",
    "roles",
    "audit_log",
    "login_throttles",
    "scheduled_tasks",
    "triggers",
    "trigger_executions",
    "runtime_configs",
    "systems",
    "file_shares",
    # ---------- heartbeats ----------
    "heartbeats",
    "heartbeat_runs",
    "heartbeat_triggers",
    # ---------- goals (trigger disabled around goal_tasks) ----------
    "missions",
    "projects",
    "goals",
    "goal_tasks",          # ← DISABLE/ENABLE trigger wraps this table
    # ---------- tickets ----------
    "tickets",
    "ticket_comments",
    "ticket_activity",
    # ---------- brain repo ----------
    "brain_repo_configs",
    # ---------- plugins ----------
    "plugin_scan_cache",
    "plugin_audit_log",
    "plugins_installed",
    "plugin_hook_circuit_state",
    "integration_health_cache",
    "plugin_orphans",
    # ---------- knowledge ----------
    "knowledge_connections",
    "knowledge_connection_events",
    "knowledge_api_keys",
]

_TRIGGER_NAME = "trg_task_done_updates_goal"
_TRIGGER_TABLE = "goal_tasks"
_STATE_TABLE = "evonexus_migration_state"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("evonexus-migrate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_datetime(val: Any) -> Optional[datetime]:
    """Parse ISO-8601 TEXT from SQLite into a UTC-aware datetime for Postgres."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    s = str(val).strip()
    if not s:
        return None
    # Try common ISO formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f+00:00",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    log.warning("Could not parse datetime value %r — storing NULL", val)
    return None


def _cast_row(
    table: str,
    row: dict[str, Any],
    is_pg_target: bool,
) -> dict[str, Any]:
    """Apply bool and datetime casts required for Postgres target."""
    if not is_pg_target:
        return row
    out = dict(row)
    bool_cols = _BOOL_COLUMNS.get(table, set())
    dt_cols = _DATETIME_COLUMNS.get(table, set())
    for col in bool_cols:
        if col in out and out[col] is not None:
            out[col] = bool(out[col])
    for col in dt_cols:
        if col in out:
            out[col] = _parse_datetime(out[col])
    return out


def _build_engine(url: str, is_source: bool = False):
    """Build a SQLAlchemy engine mirroring the URL-normalisation in db/engine.py."""
    from sqlalchemy import create_engine, event

    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    is_sqlite = url.startswith("sqlite")

    kwargs: dict[str, Any] = {"future": True}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Source PG connection (rare) gets a tiny pool; target gets a slightly
        # larger one since we do sequential-table bulk inserts.
        kwargs["pool_pre_ping"] = True
        if is_source:
            kwargs["pool_size"] = 1
            kwargs["max_overflow"] = 0

    engine = create_engine(url, **kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _rec):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=OFF")   # allow FK violations in source read
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
    return engine


def _get_columns(conn, table: str) -> list[str]:
    """Return list of column names for *table* via PRAGMA / information_schema."""
    from sqlalchemy import text, inspect

    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return [r[1] for r in rows]
    else:
        insp = inspect(conn.engine)
        return [c["name"] for c in insp.get_columns(table)]


def _table_exists(conn, table: str) -> bool:
    from sqlalchemy import text, inspect
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchone()
        return result is not None
    else:
        insp = inspect(conn.engine)
        return table in insp.get_table_names()


def _row_count(conn, table: str) -> int:
    from sqlalchemy import text
    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
    return result[0] if result else 0


def _checksum(conn, table: str, pk_col: str) -> str:
    """SHA-256 of sorted primary key values — canonical identity fingerprint."""
    from sqlalchemy import text
    rows = conn.execute(
        text(f"SELECT {pk_col} FROM {table} ORDER BY {pk_col}")
    ).fetchall()
    h = hashlib.sha256()
    for (val,) in rows:
        h.update(str(val).encode())
    return h.hexdigest()[:16]


def _get_pk_col(table: str) -> Optional[str]:
    """Return the single PK column name, or None for composite-PK tables."""
    if table in _COMPOSITE_PK_TABLES:
        return None
    if table in _NONSTANDARD_PK:
        return _NONSTANDARD_PK[table]
    # All other tables use 'id' as PK (confirmed from 0002_core_schema.py)
    return "id"


# ---------------------------------------------------------------------------
# Alembic revision check
# ---------------------------------------------------------------------------

def _alembic_head(conn) -> Optional[str]:
    from sqlalchemy import text
    try:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resumption state table
# ---------------------------------------------------------------------------

def _ensure_state_table(conn) -> None:
    from sqlalchemy import text
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {_STATE_TABLE} (
            table_name TEXT PRIMARY KEY,
            rows_copied INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT
        )
    """))
    conn.commit()


def _table_completed(conn, table: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(
        text(f"SELECT completed_at FROM {_STATE_TABLE} WHERE table_name=:t"),
        {"t": table},
    ).fetchone()
    return row is not None and row[0] is not None


def _mark_table_completed(conn, table: str, rows: int) -> None:
    from sqlalchemy import text
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(text(f"""
        INSERT INTO {_STATE_TABLE} (table_name, rows_copied, completed_at)
        VALUES (:t, :r, :ts)
        ON CONFLICT (table_name) DO UPDATE SET rows_copied=:r, completed_at=:ts
    """), {"t": table, "r": rows, "ts": now})
    conn.commit()


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def _disable_trigger(conn) -> None:
    from sqlalchemy import text
    conn.execute(text(
        f"ALTER TABLE {_TRIGGER_TABLE} DISABLE TRIGGER {_TRIGGER_NAME}"
    ))
    conn.commit()
    log.info("  trigger %s DISABLED", _TRIGGER_NAME)


def _enable_trigger(conn) -> None:
    from sqlalchemy import text
    conn.execute(text(
        f"ALTER TABLE {_TRIGGER_TABLE} ENABLE TRIGGER {_TRIGGER_NAME}"
    ))
    conn.commit()
    log.info("  trigger %s ENABLED", _TRIGGER_NAME)


def _drift_correction(conn) -> None:
    """Reconcile goals.current_value vs goal_progress_v.derived_value post-copy.

    Uses the same logic as POST /api/goals/{id}/recalculate — counts done tasks
    directly from goal_tasks, preserves 'achieved' status where target already met.
    """
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT g.id, g.current_value, g.target_value, g.status,
               COUNT(CASE WHEN gt.status = 'done' THEN 1 END) AS derived_value
        FROM goals g
        LEFT JOIN goal_tasks gt ON gt.goal_id = g.id
        GROUP BY g.id, g.current_value, g.target_value, g.status
    """)).fetchall()

    corrected = 0
    for row in rows:
        gid, cur, target, status, derived = row
        derived = derived or 0
        if cur == derived:
            continue
        new_status = status
        if derived >= (target or 0) and status == "active":
            new_status = "achieved"
        conn.execute(text("""
            UPDATE goals SET current_value=:cv, status=:st WHERE id=:id
        """), {"cv": derived, "st": new_status, "id": gid})
        corrected += 1
        log.debug("  goal %s: corrected current_value %s→%s, status %s→%s",
                  gid, cur, derived, status, new_status)

    conn.commit()
    if corrected:
        log.info("  drift correction: %d goal(s) reconciled", corrected)
    else:
        log.info("  drift correction: all goals consistent")


def _resync_sequences(target_conn) -> None:
    """Reset PG sequences for INTEGER PK tables to avoid future insert collisions."""
    from sqlalchemy import text
    for table, pk_col in _INTEGER_PK_TABLES:
        if not _table_exists(target_conn, table):
            continue
        try:
            target_conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', '{pk_col}'),
                    COALESCE((SELECT MAX({pk_col}) FROM {table}), 0) + 1,
                    false
                )
            """))
        except Exception as exc:  # noqa: BLE001
            log.debug("  seq resync skipped for %s.%s: %s", table, pk_col, exc)
    target_conn.commit()
    log.info("  PG sequences resynced for integer-PK tables")


def _migrate_table(
    src_conn,
    dst_conn,
    table: str,
    batch_size: int,
    resume: bool,
    verbose: bool,
    is_pg_target: bool,
) -> int:
    """Copy all rows from *table* in source to destination.

    Returns the number of rows actually inserted.
    """
    from sqlalchemy import text

    if resume and _table_completed(dst_conn, table):
        existing = _row_count(dst_conn, table)
        log.info("  [SKIP] %s — already completed (%d rows in target)", table, existing)
        return 0

    if not _table_exists(src_conn, table):
        log.debug("  [MISS] %s not in source — skipping", table)
        return 0

    src_cols = _get_columns(src_conn, table)
    if not src_cols:
        log.warning("  [WARN] %s has no columns — skipping", table)
        return 0

    cols_str = ", ".join(src_cols)
    pk_col = _get_pk_col(table)

    offset = 0
    total_inserted = 0

    while True:
        rows = src_conn.execute(
            text(f"SELECT {cols_str} FROM {table} LIMIT :lim OFFSET :off"),
            {"lim": batch_size, "off": offset},
        ).fetchall()
        if not rows:
            break

        batch: list[dict[str, Any]] = []
        for raw in rows:
            row_dict = dict(zip(src_cols, raw))
            row_dict = _cast_row(table, row_dict, is_pg_target)
            batch.append(row_dict)

        # Build INSERT ... ON CONFLICT DO NOTHING
        placeholders = ", ".join(f":{c}" for c in src_cols)
        if pk_col:
            conflict_clause = f"ON CONFLICT ({pk_col}) DO NOTHING"
        else:
            # Composite PK — let PG figure out the constraint
            conflict_clause = "ON CONFLICT DO NOTHING"

        insert_sql = text(
            f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) {conflict_clause}"
        )
        result = dst_conn.execute(insert_sql, batch)
        dst_conn.commit()

        # rowcount reflects actual rows inserted (skipped by ON CONFLICT = 0)
        # SQLAlchemy returns -1 if the driver doesn't support rowcount on executemany;
        # fall back to len(batch) in that case (conservative — counts attempts).
        actual_inserted = result.rowcount if result.rowcount >= 0 else len(batch)
        total_inserted += actual_inserted
        offset += len(batch)  # always advance offset by batch size
        if verbose:
            log.info("    %s: +%d rows (offset %d)", table, actual_inserted, offset)

    if resume:
        _mark_table_completed(dst_conn, table, total_inserted)

    return total_inserted


# ---------------------------------------------------------------------------
# Plugin compatibility check (ADR PG-Q7 F8)
# ---------------------------------------------------------------------------

def _check_plugin_compat(src_conn) -> list[str]:
    """Return slugs of plugins that lack a postgres migration file on the source."""
    from sqlalchemy import text
    import os

    if not _table_exists(src_conn, "plugins_installed"):
        return []

    rows = src_conn.execute(
        text("SELECT slug FROM plugins_installed WHERE status='active'")
    ).fetchall()

    incompatible: list[str] = []
    # We look relative to the repo root — heuristic based on typical layout.
    # If plugins/ folder isn't accessible, we skip the check gracefully.
    try:
        # Walk up from this file's location to find plugins/
        here = __file__
        for _ in range(5):
            here = os.path.dirname(here)
            plugins_dir = os.path.join(here, "plugins")
            if os.path.isdir(plugins_dir):
                break
        else:
            plugins_dir = None

        if plugins_dir:
            for (slug,) in rows:
                pg_file = os.path.join(plugins_dir, slug, "migrations", "install.postgres.sql")
                legacy_file = os.path.join(plugins_dir, slug, "migrations", "install.sql")
                sqlite_file = os.path.join(plugins_dir, slug, "migrations", "install.sqlite.sql")
                has_pg = os.path.isfile(pg_file)
                has_legacy_only = os.path.isfile(legacy_file) and not has_pg and not os.path.isfile(sqlite_file)
                if has_legacy_only:
                    incompatible.append(slug)
    except Exception:  # noqa: BLE001
        pass
    return incompatible


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def _dry_run(src_engine, dst_engine) -> None:
    log.info("=== DRY RUN — no data will be written ===")
    with src_engine.connect() as src_conn:
        with dst_engine.connect() as dst_conn:
            src_head = _alembic_head(src_conn)
            dst_head = _alembic_head(dst_conn)
            log.info("Source alembic revision: %s", src_head or "none")
            log.info("Target alembic revision: %s", dst_head or "none")
            total_rows = 0
            for table in TABLES_IN_ORDER:
                if not _table_exists(src_conn, table):
                    continue
                n = _row_count(src_conn, table)
                total_rows += n
                log.info("  would migrate %6d rows from %-40s", n, table)
    log.info("Total: %d rows across %d tables", total_rows, len(TABLES_IN_ORDER))
    log.info("=== DRY RUN complete — no changes made ===")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify(src_engine, dst_engine) -> bool:
    log.info("=== VERIFICATION ===")
    ok = True
    with src_engine.connect() as src_conn:
        with dst_engine.connect() as dst_conn:
            # Use the inspected table list on target to catch missed tables
            from sqlalchemy import inspect as sa_inspect
            target_tables = set(sa_inspect(dst_engine).get_table_names()) - {
                "alembic_version", _STATE_TABLE
            }
            migrated_tables = [t for t in TABLES_IN_ORDER if _table_exists(src_conn, t)]

            for table in migrated_tables:
                src_n = _row_count(src_conn, table)
                dst_n = _row_count(dst_conn, table) if table in target_tables else -1

                pk_col = _get_pk_col(table)
                if pk_col:
                    src_cs = _checksum(src_conn, table, pk_col)
                    dst_cs = _checksum(dst_conn, table, pk_col) if table in target_tables else "N/A"
                    match = src_n == dst_n and src_cs == dst_cs
                    status = "OK" if match else "DIFF"
                    log.info("  %-40s rows=%d/%d cs=%s/%s [%s]",
                             table, src_n, dst_n, src_cs, dst_cs, status)
                else:
                    match = src_n == dst_n
                    status = "OK" if match else "DIFF"
                    log.info("  %-40s rows=%d/%d (composite-pk, no checksum) [%s]",
                             table, src_n, dst_n, status)
                if not match:
                    ok = False

    if ok:
        log.info("=== VERIFICATION PASSED ===")
    else:
        log.error("=== VERIFICATION FAILED — row count or checksum mismatch ===")
    return ok


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def migrate(
    source_url: str,
    target_url: str,
    dry_run: bool = False,
    resume: bool = False,
    allow_non_empty: bool = False,
    batch_size: int = 1000,
    skip_verify: bool = False,
    verbose: bool = False,
) -> bool:
    """Run the full migration.  Returns True on success."""
    if verbose:
        log.setLevel(logging.DEBUG)

    src_engine = _build_engine(source_url, is_source=True)
    dst_engine = _build_engine(target_url, is_source=False)

    is_pg_target = not target_url.startswith("sqlite")

    if dry_run:
        _dry_run(src_engine, dst_engine)
        return True

    # -----------------------------------------------------------------------
    # Pre-flight checks
    # -----------------------------------------------------------------------
    with src_engine.connect() as src_conn:
        src_head = _alembic_head(src_conn)

    with dst_engine.connect() as dst_conn:
        dst_head = _alembic_head(dst_conn)

    log.info("Source alembic head: %s", src_head or "none")
    log.info("Target alembic head: %s", dst_head or "none")

    if src_head and dst_head and src_head != dst_head:
        log.error(
            "Alembic revision mismatch: source=%s target=%s. "
            "Run 'alembic upgrade head' on the target first.",
            src_head, dst_head,
        )
        return False

    # Plugin compatibility check (PG target only)
    if is_pg_target:
        with src_engine.connect() as src_conn:
            incompatible = _check_plugin_compat(src_conn)
        if incompatible:
            for slug in incompatible:
                log.error(
                    "Plugin %s does not support PostgreSQL. "
                    "Either upgrade to v2 (add install.postgres.sql) or "
                    "uninstall before migrating.", slug,
                )
            return False

    # Non-empty target check
    if is_pg_target and not allow_non_empty:
        with dst_engine.connect() as dst_conn:
            with dst_engine.connect() as c2:
                from sqlalchemy import inspect as sa_inspect
                tbl_list = sa_inspect(dst_engine).get_table_names()
                # Check a key table for existing data
                if "users" in tbl_list:
                    n = _row_count(dst_conn, "users")
                    if n > 0:
                        log.error(
                            "Target database is not empty (%d users found). "
                            "Use --allow-non-empty to migrate into a populated target.",
                            n,
                        )
                        return False

    # -----------------------------------------------------------------------
    # Migration
    # -----------------------------------------------------------------------
    log.info("Starting migration: %s → %s", source_url, target_url)
    total_rows = 0
    trigger_disabled = False

    try:
        with src_engine.connect() as src_conn:
            with dst_engine.connect() as dst_conn:
                if resume:
                    _ensure_state_table(dst_conn)

                for table in TABLES_IN_ORDER:
                    # Disable trigger before goal_tasks, enable after
                    if table == _TRIGGER_TABLE and is_pg_target and not trigger_disabled:
                        _disable_trigger(dst_conn)
                        trigger_disabled = True

                    log.info("Migrating: %s", table)
                    n = _migrate_table(
                        src_conn=src_conn,
                        dst_conn=dst_conn,
                        table=table,
                        batch_size=batch_size,
                        resume=resume,
                        verbose=verbose,
                        is_pg_target=is_pg_target,
                    )
                    total_rows += n
                    log.info("  → %d rows", n)

                # Re-enable trigger + drift correction
                if trigger_disabled:
                    _enable_trigger(dst_conn)
                    _drift_correction(dst_conn)

                # Resync PG sequences after bulk insert with preserved IDs
                if is_pg_target:
                    _resync_sequences(dst_conn)

    except Exception:
        # If trigger was disabled but we crashed, re-enable it before exiting
        if trigger_disabled:
            try:
                with dst_engine.connect() as dst_conn:
                    _enable_trigger(dst_conn)
            except Exception:  # noqa: BLE001
                log.error("CRITICAL: could not re-enable trigger after error. "
                          "Run manually: ALTER TABLE goal_tasks ENABLE TRIGGER %s",
                          _TRIGGER_NAME)
        raise

    log.info("Migration complete: %d rows total", total_rows)
    if total_rows == 0:
        log.info("(All rows already present — migration was a no-op)")

    # -----------------------------------------------------------------------
    # Verification
    # -----------------------------------------------------------------------
    if not skip_verify:
        ok = _verify(src_engine, dst_engine)
        return ok

    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate EvoNexus data from SQLite to PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source", required=True,
        help="Source database URL (e.g. sqlite:////path/to/dashboard.db)",
    )
    parser.add_argument(
        "--target", required=True,
        help="Target database URL (e.g. postgresql://user:pass@host/db)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count rows and check connectivity without writing anything.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume an interrupted migration from the last completed table.",
    )
    parser.add_argument(
        "--allow-non-empty", action="store_true",
        help="Allow migration into a non-empty target database.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000,
        help="Rows per INSERT batch (default: 1000).",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="Skip post-migration row-count + checksum verification.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-batch progress.",
    )
    args = parser.parse_args()

    success = migrate(
        source_url=args.source,
        target_url=args.target,
        dry_run=args.dry_run,
        resume=args.resume,
        allow_non_empty=args.allow_non_empty,
        batch_size=args.batch_size,
        skip_verify=args.skip_verify,
        verbose=args.verbose,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
