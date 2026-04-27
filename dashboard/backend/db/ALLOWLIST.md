# sqlite3 Allowlist — dashboard backend

> **Purpose:** CI Guard 1 (`ci-postgres.yml`) blocks all `sqlite3.connect` and `import sqlite3`
> outside the declared allowlist paths. Every remaining use of raw sqlite3 in the codebase
> must be justified here. "Allowlisted" means: correct for SQLite, intentionally deferred to
> a later step for PostgreSQL compatibility, or permanently out-of-scope.
>
> **Allowlist path patterns (matched by Guard 1):**
> - `dashboard/backend/db/` — this directory; houses the engine/session abstraction layer
> - `dashboard/alembic/env.py` — Alembic migration runner (manages its own connection)
> - `dashboard/backend/knowledge/` — knowledge module has its own SQLite abstraction (out-of-scope)
> - `tests/fixtures/` — test fixtures may use raw sqlite3 for fixture setup

---

## Entries

### 1. `dashboard/backend/plugin_migrator.py` — `import sqlite3`

**Classification:** HIGH-PRIORITY — Step 2  
**Reason:** `plugin_migrator.run_sql_transactional()` accepts a raw `sqlite3.Connection` and
executes plugin-supplied DDL statements (CREATE TABLE, etc.) in a single transaction.
The SQLite `sqlite3.Connection` API (`executescript`, `isolation_level`) has no direct
SQLAlchemy equivalent for arbitrary DDL bundles. The plugin migration engine will be
replaced by Alembic-based plugin migrations in Step 2.

---

### 2. `dashboard/backend/plugin_install_state.py:173` — `sqlite3.connect()` in `rollback_from_state()`

**Classification:** HIGH-PRIORITY — Step 2  
**Reason:** Rollback during plugin install passes a raw `sqlite3.Connection` to
`plugin_migrator.run_sql_transactional()` to execute `uninstall.sql`. Shares the same
DDL-engine dependency as entry 1. Migrated when plugin_migrator is ported in Step 2.

---

### 3. `dashboard/backend/routes/plugins.py:947` — `sqlite3.connect()` in SQL install

**Classification:** HIGH-PRIORITY — Step 2  
**Reason:** Plugin install path opens a connection and passes it to `install_plugin_sql()`
(which delegates to `plugin_migrator`). Same DDL-engine dependency. Step 2 will introduce
a dialect-aware migration runner.

---

### 4. `dashboard/backend/routes/plugins.py:1387,1388` — `sqlite3.connect()` for `Connection.backup()`

**Classification:** OUT-OF-SCOPE (SQLite-only feature)  
**Reason:** `Connection.backup()` is a SQLite-specific API with no PostgreSQL equivalent.
This call is inside the Vault B3 plugin sandbox read-only DB snapshot path, guarded by
dialect check. On PostgreSQL, the code path uses `pg_dump` instead (implemented in Step 3).
These two lines will remain SQLite-only permanently.

---

### 5. `dashboard/backend/routes/plugins.py:1584` — `sqlite3.connect()` in SQL uninstall

**Classification:** HIGH-PRIORITY — Step 2  
**Reason:** Plugin uninstall path mirrors the install path (entry 3). Delegates to
`uninstall_plugin_sql()` which calls `plugin_migrator.run_sql_transactional()`.
Migrated in Step 2 alongside the install path.

---

### 6. `dashboard/backend/routes/backups.py:30` — `sqlite3.connect()` in `_post_restore_migrate()`

**Classification:** OUT-OF-SCOPE (SQLite-only feature)  
**Reason:** `_post_restore_migrate()` runs after a SQLite backup restore. It uses
`PRAGMA table_info()` (SQLite-only) to inspect and repair legacy schemas. This function
is intentionally SQLite-only — backup/restore on PostgreSQL uses `pg_dump`/`pg_restore`
(implemented in Step 3). The function itself is guarded: it is never called on PG backends.

---

### 7. `dashboard/backend/routes/knowledge.py:116` — `sqlite3.connect()` in `_get_sqlite()`

**Classification:** OUT-OF-SCOPE  
**Reason:** The knowledge module maintains its own SQLite connection abstraction separate
from the main dashboard DB. `_get_sqlite()` connects to the knowledge vector store
(not `evonexus.db`). The knowledge module's SQLite usage is explicitly out-of-scope for
the postgres-compat migration (see ADR-PG-Q10). Guard 1 excludes `knowledge/` path entirely
via the `dashboard/backend/knowledge/` allowlist pattern; this entry covers the dashboard
`routes/knowledge.py` shim that calls the knowledge module.

---

### 8. `dashboard/backend/app.py:144` — `_sqlite3.connect()` in boot migration

**Classification:** HIGH-PRIORITY — Step 2 (remove when Alembic owns schema)  
**Reason:** Boot-time legacy schema repair (add missing columns, fix NULL datetimes).
Guarded by `if not _is_pg_backend:` — never runs on PostgreSQL. When Alembic takes
over schema management in Step 2, this entire block will be removed and replaced by
the `0002_schema_baseline.py` migration.

---

## datetime('now') Inventory (PG-Q2)

Six occurrences of SQLite-specific `datetime('now')` — annotated here; **not migrated in Step 1**.
One additional occurrence in the knowledge module (out-of-scope SQLite-only module).

| Site | File:Line | Migration strategy |
|------|-----------|-------------------|
| 1 | `ticket_janitor.py:40` | Replace with Python `datetime.utcnow()` (Step 2) |
| 2 | `app.py:252` | Inside SQLite trigger body — replaced by dialect-aware trigger in Step 2 (PG-Q3) |
| 3 | `app.py:638` | Inside `if not _is_pg_backend:` startup migration — removed when Alembic takes over (Step 2) |
| 4 | `app.py:639` | Same block as site 3 |
| 5 | `routes/backups.py:42` | Inside `_post_restore_migrate()` — stays SQLite-only (guarded; see entry 6 above) |
| 6 | `routes/backups.py:43` | Same function as site 5 |
| 7 | `knowledge/api_keys.py:228` | SQLite-only module — see entry 9 below |

**Decision (PG-Q2):** Sites 2, 3, 4, 5, 6 remain SQLite-only via dialect guard.
Site 1 (`ticket_janitor.py`) is the only site that runs unconditionally — it will be
migrated to `datetime.utcnow(timezone.utc)` in Step 2.
Site 7 (`knowledge/api_keys.py`) is in a SQLite-only module (see entry 9) — no migration needed.

---

### 9. `dashboard/backend/knowledge/api_keys.py:228` — `datetime('now')` in `verify_token()`

**Classification:** OUT-OF-SCOPE (SQLite-only module)
**Reason:** `knowledge/api_keys.py` uses raw `sqlite3.Connection` throughout (see `_connect()`),
connects to the knowledge vector store via `connection_pool._resolve_sqlite_db_path()`, and issues
`PRAGMA journal_mode=WAL` — all structurally incompatible with PostgreSQL. This module operates on
an **isolated SQLite database** that is separate from the main `evonexus.db` (or PG equivalent).
The `datetime('now')` on line 228 is inside a raw `sqlite3.execute()` call and will never run
against the main PostgreSQL backend.

Guard 1 excludes `dashboard/backend/knowledge/` entirely via the allowlist path pattern, so the
`import sqlite3` and `sqlite3.connect()` calls are already covered. This entry documents the
`datetime('now')` occurrence specifically for PG-Q2 traceability.
