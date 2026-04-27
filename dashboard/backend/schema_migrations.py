from __future__ import annotations

from sqlalchemy import inspect


def _table_names(connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def _column_names(connection, table_name: str) -> set[str]:
    if table_name not in _table_names(connection):
        return set()
    return {column["name"] for column in inspect(connection).get_columns(table_name)}


def _scalar(connection, sql: str, params: tuple | dict | None = None):
    result = connection.exec_driver_sql(sql, params or ())
    row = result.fetchone()
    return row[0] if row else None


def _execute(connection, sql: str, params: tuple | dict | None = None) -> None:
    connection.exec_driver_sql(sql, params or ())


def upgrade_app_schema(connection) -> None:
    """Apply the schema drift fixes that used to live inline in app.py."""

    tables = _table_names(connection)
    dialect_name = getattr(getattr(connection, "dialect", None), "name", "sqlite")
    is_postgres = dialect_name == "postgresql"
    current_ts = "CURRENT_TIMESTAMP" if is_postgres else "datetime('now')"

    if "roles" in tables:
        role_cols = _column_names(connection, "roles")
        if "agent_access_json" not in role_cols:
            _execute(connection, "ALTER TABLE roles ADD COLUMN agent_access_json TEXT DEFAULT '{\"mode\": \"all\"}'")
        if "workspace_folders_json" not in role_cols:
            _execute(connection, "ALTER TABLE roles ADD COLUMN workspace_folders_json TEXT DEFAULT '{\"mode\": \"all\"}'")

    # Goal cascade helpers: keep the view and trigger available on every boot.
    if "goals" in tables and "goal_tasks" in tables:
        _execute(
            connection,
            """
            CREATE VIEW IF NOT EXISTS goal_progress_v AS
            SELECT g.id as goal_id, g.slug, g.target_value,
                   COUNT(t.id) as total_tasks,
                   COUNT(CASE WHEN t.status='done' THEN 1 END) as done_tasks,
                   CASE WHEN COUNT(t.id) > 0
                        THEN CAST(COUNT(CASE WHEN t.status='done' THEN 1 END) AS REAL) / COUNT(t.id) * 100.0
                        ELSE 0 END as pct_complete
            FROM goals g LEFT JOIN goal_tasks t ON t.goal_id = g.id
            GROUP BY g.id;
            """,
        )
        if is_postgres:
            _execute(
                connection,
                """
                CREATE OR REPLACE FUNCTION trg_task_done_updates_goal_fn()
                RETURNS trigger AS $$
                BEGIN
                  IF NEW.goal_id IS NOT NULL AND NEW.status = 'done' AND OLD.status <> 'done' THEN
                    UPDATE goals
                    SET current_value = current_value + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = NEW.goal_id;
                    UPDATE goals
                    SET status = 'achieved'
                    WHERE id = NEW.goal_id AND current_value >= target_value AND status = 'active';
                  END IF;
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """,
            )
            _execute(
                connection,
                """
                CREATE TRIGGER trg_task_done_updates_goal
                AFTER UPDATE OF status ON goal_tasks
                FOR EACH ROW
                EXECUTE FUNCTION trg_task_done_updates_goal_fn();
                """,
            )
        else:
            _execute(
                connection,
                """
                CREATE TRIGGER IF NOT EXISTS trg_task_done_updates_goal
                AFTER UPDATE OF status ON goal_tasks
                WHEN NEW.goal_id IS NOT NULL AND NEW.status = 'done' AND OLD.status != 'done'
                BEGIN
                  UPDATE goals SET current_value = current_value + 1, updated_at = datetime('now') WHERE id = NEW.goal_id;
                  UPDATE goals SET status = 'achieved' WHERE id = NEW.goal_id AND current_value >= target_value AND status = 'active';
                END;
                """,
            )

        mission_count = _scalar(connection, "SELECT COUNT(*) FROM missions")
        if mission_count == 0:
            _now_seed = "2026-04-14T00:00:00.000000Z"
            _execute(
                connection,
                """
                INSERT INTO missions (slug, title, description, target_metric, target_value, current_value, due_date, status, created_at, updated_at)
                VALUES ('evo-revenue-1m-q4-2026', 'Evolution Revenue $1M Q4 2026',
                        'Atingir $1M de receita anual até o Q4 2026',
                        'revenue_usd', 1000000, 0, '2026-12-31', 'active', ?, ?)
                """,
                (_now_seed, _now_seed),
            )
            mission_id = _scalar(connection, "SELECT id FROM missions WHERE slug = 'evo-revenue-1m-q4-2026'")
            for slug, title, description in [
                ("evo-ai", "Evo AI", "CRM + AI agents — produto principal"),
                ("evo-summit", "Evolution Summit", "Evento de lançamento (14-16 Abr 2026)"),
                ("evo-academy", "Evo Academy", "Plataforma de cursos"),
            ]:
                _execute(
                    connection,
                    """
                    INSERT INTO projects (slug, mission_id, title, description, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (slug, mission_id, title, description, _now_seed, _now_seed),
                )

            project_ids = {
                "evo-ai": _scalar(connection, "SELECT id FROM projects WHERE slug = 'evo-ai'"),
                "evo-summit": _scalar(connection, "SELECT id FROM projects WHERE slug = 'evo-summit'"),
                "evo-academy": _scalar(connection, "SELECT id FROM projects WHERE slug = 'evo-academy'"),
            }
            goals_seed = [
                ("evo-ai-100-customers", project_ids["evo-ai"], "100 paying customers by Jun 30", "customers", "count", 100, "2026-06-30"),
                ("evo-ai-billing-v2", project_ids["evo-ai"], "Ship billing v2", "shipped", "boolean", 1, "2026-05-31"),
                ("evo-summit-200-tickets", project_ids["evo-summit"], "Sell 200 tickets", "tickets_sold", "count", 200, "2026-04-13"),
                ("evo-summit-3-sponsors", project_ids["evo-summit"], "Close 3 sponsors", "sponsors", "count", 3, "2026-04-10"),
                ("evo-academy-50-students", project_ids["evo-academy"], "50 beta students", "students", "count", 50, "2026-06-30"),
            ]
            for slug, project_id, title, target_metric, metric_type, target_value, due_date in goals_seed:
                _execute(
                    connection,
                    """
                    INSERT INTO goals (slug, project_id, title, target_metric, metric_type, target_value, current_value, status, created_at, updated_at, due_date)
                    VALUES (?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)
                    """,
                    (slug, project_id, title, target_metric, metric_type, target_value, _now_seed, _now_seed, due_date),
                )

    if "tickets" in tables:
        ticket_cols = _column_names(connection, "tickets")
        for column_name, ddl in [
            ("source_agent", "ALTER TABLE tickets ADD COLUMN source_agent TEXT"),
            ("source_session_id", "ALTER TABLE tickets ADD COLUMN source_session_id TEXT"),
            ("workspace_path", "ALTER TABLE tickets ADD COLUMN workspace_path TEXT"),
            ("memory_md_path", "ALTER TABLE tickets ADD COLUMN memory_md_path TEXT"),
            ("thread_session_id", "ALTER TABLE tickets ADD COLUMN thread_session_id TEXT"),
            ("message_count", "ALTER TABLE tickets ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0"),
            ("last_summary_at_message", "ALTER TABLE tickets ADD COLUMN last_summary_at_message INTEGER NOT NULL DEFAULT 0"),
        ]:
            if column_name not in ticket_cols:
                _execute(connection, ddl)
                ticket_cols.add(column_name)

    if "users" in tables:
        user_cols = _column_names(connection, "users")
        if "totp_secret" not in user_cols:
            _execute(connection, "ALTER TABLE users ADD COLUMN totp_secret TEXT")
        if "totp_enabled" not in user_cols:
            _execute(
                connection,
                "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE" if is_postgres else "ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0",
            )
        if "totp_last_used_step" not in user_cols:
            _execute(connection, "ALTER TABLE users ADD COLUMN totp_last_used_step INTEGER")
        if "totp_confirmed_at" not in user_cols:
            _execute(connection, "ALTER TABLE users ADD COLUMN totp_confirmed_at TIMESTAMP" if is_postgres else "ALTER TABLE users ADD COLUMN totp_confirmed_at TEXT")

    # Knowledge tables are managed outside SQLAlchemy models, so keep them here.
    if "knowledge_connections" not in tables:
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS knowledge_connections (
                id TEXT PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                connection_string_encrypted BLOB,
                host TEXT,
                port INTEGER,
                database_name TEXT,
                username TEXT,
                ssl_mode TEXT,
                status TEXT DEFAULT 'disconnected',
                schema_version TEXT,
                pgvector_version TEXT,
                postgres_version TEXT,
                last_health_check TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
        )
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS knowledge_connection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id TEXT REFERENCES knowledge_connections(id) ON DELETE CASCADE,
                event_type TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
        )
        _execute(connection, "CREATE INDEX IF NOT EXISTS idx_kconn_status ON knowledge_connections(status)")
        _execute(
            connection,
            "CREATE INDEX IF NOT EXISTS idx_kconn_events_conn ON knowledge_connection_events(connection_id, created_at)",
        )

    if "knowledge_api_keys" not in tables:
        _execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS knowledge_api_keys (
                id TEXT PRIMARY KEY,
                name TEXT,
                prefix TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                connection_id TEXT NOT NULL,
                space_ids TEXT NOT NULL DEFAULT '[]',
                scopes TEXT NOT NULL DEFAULT '["read"]',
                rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
                rate_limit_per_day INTEGER NOT NULL DEFAULT 10000,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                expires_at TEXT
            );
            """,
        )
        _execute(connection, "CREATE INDEX IF NOT EXISTS idx_kak_prefix ON knowledge_api_keys(prefix)")

    # Fix corrupted datetime columns that can crash SQLAlchemy on load.
    for table_name, column_name in [("roles", "created_at"), ("users", "created_at"), ("users", "last_login")]:
        try:
            if column_name in _column_names(connection, table_name):
                _execute(
                    connection,
                    f"UPDATE {table_name} SET {column_name} = {current_ts} WHERE {column_name} IS NOT NULL AND typeof({column_name}) != 'text'" if not is_postgres else f"UPDATE {table_name} SET {column_name} = CURRENT_TIMESTAMP WHERE {column_name} IS NOT NULL",
                )
                _execute(
                    connection,
                    f"UPDATE {table_name} SET {column_name} = {current_ts} WHERE {column_name} IS NOT NULL AND {column_name} != '' AND {column_name} NOT LIKE '____-__-__%'" if not is_postgres else f"UPDATE {table_name} SET {column_name} = CURRENT_TIMESTAMP WHERE {column_name} IS NOT NULL",
                )
        except Exception:
            pass


def downgrade_app_schema(connection) -> None:
    """Drop the schema additions managed by upgrade_app_schema."""

    dialect_name = getattr(getattr(connection, "dialect", None), "name", "sqlite")
    is_postgres = dialect_name == "postgresql"

    if is_postgres:
        for sql in [
            "DROP TRIGGER IF EXISTS trg_task_done_updates_goal ON goal_tasks",
            "DROP FUNCTION IF EXISTS trg_task_done_updates_goal_fn()",
            "DROP VIEW IF EXISTS goal_progress_v",
            "DROP TABLE IF EXISTS knowledge_api_keys",
            "DROP TABLE IF EXISTS knowledge_connection_events",
            "DROP TABLE IF EXISTS knowledge_connections",
        ]:
            try:
                _execute(connection, sql)
            except Exception:
                pass
        return

    for sql in [
        "DROP TRIGGER IF EXISTS trg_task_done_updates_goal",
        "DROP VIEW IF EXISTS goal_progress_v",
        "DROP TABLE IF EXISTS knowledge_api_keys",
        "DROP TABLE IF EXISTS knowledge_connection_events",
        "DROP TABLE IF EXISTS knowledge_connections",
    ]:
        try:
            _execute(connection, sql)
        except Exception:
            pass
