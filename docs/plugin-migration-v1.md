# Plugin Migration Guide — v1.0.0 Breaking Change

This guide is for authors of EvoNexus plugins that ship SQL migrations.

EvoNexus v1.0.0 adds PostgreSQL as an opt-in database backend alongside
the existing SQLite default.  Because SQLite and PostgreSQL use incompatible
SQL dialects for several common constructs, a single `install.sql` that
targets SQLite will **fail at install time on a Postgres-backed EvoNexus
instance**.

---

## What changed

Prior to v1.0.0 the plugin contract defined a single migration file:

```
migrations/install.sql
migrations/uninstall.sql
```

From v1.0.0 onward the loader selects the migration file by backend dialect:

| Active backend | File resolved | Notes |
|---|---|---|
| SQLite (default) | `migrations/install.sqlite.sql` | preferred |
| SQLite (legacy) | `migrations/install.sql` | accepted with `DeprecationWarning` |
| PostgreSQL | `migrations/install.postgres.sql` | required; no fallback |

**Timeline:**

- **v1.0.0** (now) — legacy `install.sql` works on SQLite with a deprecation
  warning; on Postgres it fails-fast with `PluginCompatError`.
- **v1.1.0** — legacy `install.sql` fallback removed.  Plugins that have not
  migrated will fail to install on both backends.

The same rule applies to `uninstall.sql` and any future hook SQL files.

---

## Migration steps

1. Rename `migrations/install.sql` → `migrations/install.sqlite.sql`
2. Create `migrations/install.postgres.sql` (see translation table below)
3. Rename `migrations/uninstall.sql` → `migrations/uninstall.sqlite.sql`
4. Create `migrations/uninstall.postgres.sql`
5. Remove the original `migrations/install.sql` and `migrations/uninstall.sql`

Do **not** keep the old `install.sql` alongside the new dialect files —
the loader selects by presence; the legacy file is only a fallback for
third-party plugins that have not yet migrated.

---

## SQLite → PostgreSQL translation reference

### ID generation (random hex strings)

SQLite-only:
```sql
id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8))))
```

PostgreSQL equivalent (no extension required):
```sql
id TEXT PRIMARY KEY DEFAULT (md5(random()::text || clock_timestamp()::text))
```

Alternative if `pgcrypto` extension is available:
```sql
id TEXT PRIMARY KEY DEFAULT (gen_random_uuid()::text)
```

Per ADR PG-Q10, EvoNexus stores IDs as `VARCHAR(32)` TEXT on both backends;
do not use the native `UUID` type — it breaks SQLite parity.

### Timestamps

SQLite-only:
```sql
created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
```

PostgreSQL equivalent:
```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
```

Note: on SQLite the column type is `TEXT` (ISO-8601 stored as string).
On PostgreSQL the column type is `TIMESTAMPTZ`.  SQLAlchemy `DateTime(timezone=True)`
maps to the correct type on each backend automatically.

If you need to store as TEXT on both backends for simplicity:
```sql
-- PostgreSQL TEXT-ISO fallback (acceptable, loses index range queries)
created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'))
```

### Upsert / idempotent inserts

SQLite-only:
```sql
INSERT OR IGNORE INTO my_table (id, name) VALUES ('seed-1', 'Example');
```

PostgreSQL equivalent:
```sql
INSERT INTO my_table (id, name) VALUES ('seed-1', 'Example')
    ON CONFLICT DO NOTHING;
```

When the conflict target is a specific column (e.g. a UNIQUE constraint other
than the primary key), name it explicitly:
```sql
INSERT INTO my_table (name) VALUES ('Example')
    ON CONFLICT (name) DO NOTHING;
```

### Auto-increment integer primary keys

SQLite-only:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
```

PostgreSQL equivalents (pick one):
```sql
-- Option A: BIGSERIAL (shorthand, recommended)
id BIGSERIAL PRIMARY KEY

-- Option B: GENERATED ALWAYS AS IDENTITY (SQL standard)
id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
```

### SQLite PRAGMA statements

Remove all `PRAGMA` statements from your PostgreSQL migration file.
`PRAGMA foreign_keys = ON` is a per-connection SQLite directive — PostgreSQL
enforces foreign keys by default.

### SQLite-only date arithmetic

SQLite-only:
```sql
WHEN julianday('now') - julianday(OLD.last_consultation_at) < 7300
```

PostgreSQL equivalent:
```sql
WHEN (CURRENT_TIMESTAMP - OLD.last_consultation_at::timestamptz) < INTERVAL '7300 days'
```

For `is_minor` age checks:
```sql
-- SQLite
WHEN (julianday('now') - julianday(NEW.dob) < 6570)
-- PostgreSQL
WHEN (CURRENT_DATE - NEW.dob::date) < 6570
```

### Boolean columns

SQLite stores booleans as `INTEGER NOT NULL DEFAULT 0`.  PostgreSQL has a
native `BOOLEAN` type:

SQLite:
```sql
is_minor INTEGER NOT NULL DEFAULT 0 CHECK (is_minor IN (0, 1))
```

PostgreSQL:
```sql
is_minor BOOLEAN NOT NULL DEFAULT FALSE
```

### Triggers

SQLite triggers use a different syntax from PostgreSQL.  PostgreSQL requires
a separate trigger function written in PL/pgSQL.

SQLite example:
```sql
CREATE TRIGGER IF NOT EXISTS trg_my_trigger
AFTER INSERT ON my_table
FOR EACH ROW
BEGIN
    UPDATE other_table SET count = count + 1 WHERE id = NEW.ref_id;
END;
```

PostgreSQL equivalent:
```sql
CREATE OR REPLACE FUNCTION fn_my_trigger()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE other_table SET count = count + 1 WHERE id = NEW.ref_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_my_trigger
AFTER INSERT ON my_table
FOR EACH ROW EXECUTE FUNCTION fn_my_trigger();
```

SQLite `RAISE(ABORT, 'message')` in a trigger body becomes:
```sql
-- PostgreSQL
RAISE EXCEPTION 'message';
```

Note: `IF NOT EXISTS` is not supported for triggers in PostgreSQL.  Use
`CREATE OR REPLACE` for the function; for the trigger, drop and recreate:
```sql
DROP TRIGGER IF EXISTS trg_my_trigger ON my_table;
CREATE TRIGGER trg_my_trigger ...;
```

### Partial / conditional indexes

SQLite:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_foo_unique ON foo(col) WHERE col IS NOT NULL;
```

PostgreSQL — identical syntax (partial indexes are standard):
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_foo_unique ON foo(col) WHERE col IS NOT NULL;
```

This construct is portable — no change needed.

---

## Worked example: pm-essentials

### install.sqlite.sql (rename from install.sql, no changes needed)

```sql
-- PM Essentials — initial schema + seed data (SQLite)
CREATE TABLE IF NOT EXISTS pm_essentials_projects (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'completed', 'archived', 'on_hold')),
    due_date    TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- ... (full existing content unchanged)
```

### install.postgres.sql (new file)

```sql
-- PM Essentials — initial schema + seed data (PostgreSQL)
CREATE TABLE IF NOT EXISTS pm_essentials_projects (
    id          TEXT PRIMARY KEY DEFAULT (md5(random()::text || clock_timestamp()::text)),
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'completed', 'archived', 'on_hold')),
    due_date    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
);

CREATE TABLE IF NOT EXISTS pm_essentials_sprints (
    id          TEXT PRIMARY KEY DEFAULT (md5(random()::text || clock_timestamp()::text)),
    project_id  TEXT REFERENCES pm_essentials_projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planned'
                     CHECK (status IN ('planned', 'active', 'completed')),
    goal        TEXT,
    started_at  TIMESTAMPTZ,
    ended_at    TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
);

CREATE TABLE IF NOT EXISTS pm_essentials_tasks (
    id          TEXT PRIMARY KEY DEFAULT (md5(random()::text || clock_timestamp()::text)),
    project_id  TEXT NOT NULL REFERENCES pm_essentials_projects(id) ON DELETE CASCADE,
    sprint_id   TEXT REFERENCES pm_essentials_sprints(id) ON DELETE SET NULL,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'todo'
                     CHECK (status IN ('todo', 'in_progress', 'review', 'done', 'cancelled')),
    priority    TEXT NOT NULL DEFAULT 'medium'
                     CHECK (priority IN ('urgent', 'high', 'medium', 'low')),
    assignee    TEXT,
    due_date    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_pm_essentials_tasks_project
    ON pm_essentials_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_essentials_tasks_sprint
    ON pm_essentials_tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_pm_essentials_projects_status
    ON pm_essentials_projects(status);

-- Seed data: INSERT OR IGNORE → ON CONFLICT DO NOTHING
INSERT INTO pm_essentials_projects (id, name, description, status, due_date) VALUES
    ('seed-billing',    'Billing v2',          'Revamp checkout and invoice flows',   'active',  '2026-06-30'),
    ('seed-onboarding', 'Onboarding Redesign', 'Cut drop-off in first-run setup',     'active',  '2026-05-15'),
    ('seed-docs',       'Docs Portal',         'Unified public documentation portal', 'on_hold', '2026-07-31')
ON CONFLICT DO NOTHING;

INSERT INTO pm_essentials_sprints (id, project_id, name, status, goal, started_at) VALUES
    ('seed-sprint-1', 'seed-billing', 'Sprint 1 — Checkout core', 'active',
     'Ship v2 checkout to 10% of customers with full instrumentation',
     now() AT TIME ZONE 'UTC' - INTERVAL '3 days')
ON CONFLICT DO NOTHING;

INSERT INTO pm_essentials_tasks
    (id, project_id, sprint_id, title, status, priority, assignee) VALUES
    ('seed-task-1', 'seed-billing',    'seed-sprint-1', 'Wire new Stripe price IDs',    'done',        'high',   'davidson'),
    ('seed-task-2', 'seed-billing',    'seed-sprint-1', 'Checkout page redesign',       'in_progress', 'high',   'gui'),
    ('seed-task-3', 'seed-billing',    'seed-sprint-1', 'Server-side idempotency keys', 'in_progress', 'urgent', 'nick'),
    ('seed-task-4', 'seed-billing',    'seed-sprint-1', 'Webhook retry logic',          'review',      'medium', 'davidson'),
    ('seed-task-5', 'seed-billing',    'seed-sprint-1', 'Analytics funnel events',      'todo',        'medium', 'danilo'),
    ('seed-task-6', 'seed-billing',    'seed-sprint-1', 'Feature flag for 10% rollout', 'todo',        'high',   'nick'),
    ('seed-task-7', 'seed-onboarding', NULL,            'First-run checklist copy',     'todo',        'low',    NULL),
    ('seed-task-8', 'seed-onboarding', NULL,            'Replace tour library',         'todo',        'medium', 'gui')
ON CONFLICT DO NOTHING;
```

---

## Worked example: nutri (selected patterns)

The nutri plugin has complex triggers; here are the key translations.

### Timestamp defaults

SQLite:
```sql
created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
```
PostgreSQL:
```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
```

### Boolean columns

SQLite:
```sql
patient_portal_require_pin INTEGER NOT NULL DEFAULT 0 CHECK (patient_portal_require_pin IN (0, 1))
is_minor                   INTEGER NOT NULL DEFAULT 0 CHECK (is_minor IN (0, 1))
is_cross_nutritionist_access INTEGER NOT NULL DEFAULT 0 CHECK (is_cross_nutritionist_access IN (0, 1))
is_no_show                 INTEGER NOT NULL DEFAULT 0 CHECK (is_no_show IN (0, 1))
```
PostgreSQL:
```sql
patient_portal_require_pin BOOLEAN NOT NULL DEFAULT FALSE
is_minor                   BOOLEAN NOT NULL DEFAULT FALSE
is_cross_nutritionist_access BOOLEAN NOT NULL DEFAULT FALSE
is_no_show                 BOOLEAN NOT NULL DEFAULT FALSE
```

### Auto-increment audit log PK

SQLite:
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
```
PostgreSQL:
```sql
id BIGSERIAL PRIMARY KEY
```

### Trigger: block delete on retention period

SQLite:
```sql
CREATE TRIGGER IF NOT EXISTS trg_nutri_patients_block_delete_retention
BEFORE DELETE ON nutri_patients
FOR EACH ROW
WHEN OLD.last_consultation_at IS NOT NULL
     AND julianday('now') - julianday(OLD.last_consultation_at) < 7300
BEGIN
    SELECT RAISE(ABORT, 'Lei 13.787/2018: retenção mínima de 20 anos.');
END;
```

PostgreSQL:
```sql
CREATE OR REPLACE FUNCTION fn_nutri_patients_block_delete_retention()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.last_consultation_at IS NOT NULL
       AND (CURRENT_TIMESTAMP - OLD.last_consultation_at::timestamptz) < INTERVAL '7300 days'
    THEN
        RAISE EXCEPTION 'Lei 13.787/2018: retenção mínima de 20 anos. Use status=archived.';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_nutri_patients_block_delete_retention ON nutri_patients;
CREATE TRIGGER trg_nutri_patients_block_delete_retention
BEFORE DELETE ON nutri_patients
FOR EACH ROW EXECUTE FUNCTION fn_nutri_patients_block_delete_retention();
```

### Trigger: audit log append-only enforcement

SQLite:
```sql
CREATE TRIGGER IF NOT EXISTS trg_nutri_audit_log_no_update
BEFORE UPDATE ON nutri_audit_log
BEGIN
    SELECT RAISE(ABORT, 'nutri_audit_log is append-only (LGPD Art. 9).');
END;
```

PostgreSQL:
```sql
CREATE OR REPLACE FUNCTION fn_nutri_audit_log_no_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'nutri_audit_log is append-only (LGPD Art. 9). Updates blocked.';
END;
$$;

DROP TRIGGER IF EXISTS trg_nutri_audit_log_no_update ON nutri_audit_log;
CREATE TRIGGER trg_nutri_audit_log_no_update
BEFORE UPDATE ON nutri_audit_log
FOR EACH ROW EXECUTE FUNCTION fn_nutri_audit_log_no_update();
```

---

## Testing your plugin on both backends

### SQLite (default, no setup needed)

```bash
# Ensure no DATABASE_URL is set
unset DATABASE_URL
pytest tests/ -m 'not postgres' --tb=short
```

### PostgreSQL (Docker)

```bash
docker run -d --name pg-test -e POSTGRES_PASSWORD=test -p 55436:5432 postgres:16
sleep 3
DATABASE_URL='postgresql://postgres:test@localhost:55436/postgres' \
    bash -c "cd dashboard && alembic upgrade head"
DATABASE_URL='postgresql://postgres:test@localhost:55436/postgres' \
    pytest tests/ -m postgres --tb=short
docker rm -f pg-test
```

### Running the plugin SQL manually

```bash
# SQLite
sqlite3 /tmp/test.db < plugins/my-plugin/migrations/install.sqlite.sql

# PostgreSQL
psql postgresql://postgres:test@localhost:55436/postgres \
    -f plugins/my-plugin/migrations/install.postgres.sql
```

---

## Connection pool sizing (Postgres operators)

When running EvoNexus with Postgres, the total connection count is:

```
total = (gunicorn_workers + 1 janitor + 1 dispatcher + concurrent_heartbeat_subprocesses)
      × (EVONEXUS_DB_POOL_SIZE + EVONEXUS_DB_MAX_OVERFLOW)
```

Keep `total ≤ provider_max_connections × 0.7`.

| Provider | max_conn | Recommended (1 worker) | Recommended (4 workers) |
|---|---|---|---|
| Supabase free | 60 | pool=5, overflow=10 | pool=3, overflow=4 |
| Neon free | 100 | pool=5, overflow=10 | pool=5, overflow=8 |
| Self-hosted (≥100) | 100+ | pool=10, overflow=20 | pool=5, overflow=10 |

Override via environment:
```bash
EVONEXUS_DB_POOL_SIZE=3
EVONEXUS_DB_MAX_OVERFLOW=4
```

---

## Migrating with incompatible plugins still installed

If you need to migrate core data to PostgreSQL before external plugin
repositories have been updated to include `install.postgres.sql`, use the
`--skip-incompatible-plugins` flag.

### What the flag does

- Plugins that lack `install.postgres.sql` are **warned about but do not abort
  the migration**.
- Plugin-specific tables (e.g. `pm_essentials_projects`, `nutri_patients`) are
  **skipped** — they don't exist on the PG target because the plugin's PG schema
  was never applied.
- The plugin registry row in `plugins_installed` **is migrated** so the
  dashboard continues to recognise the plugin as installed.
- A warning summary is printed at the end listing every skipped plugin.
- Verification reports skipped tables as `SKIP` (not `DIFF`) so `VERIFICATION
  PASSED` is still achievable.

### Recommended workflow

1. **Run the migration with the flag:**

   ```bash
   make db-migrate-skip-plugins \
     SOURCE=sqlite:///dashboard/data/evonexus.db \
     TARGET=postgresql://postgres:pass@localhost:5432/evonexus
   ```

   The migration completes with warnings like:

   ```
   WARN Plugin pm-essentials skipped — install.postgres.sql missing. ...
   SKIP table pm_essentials_projects (plugin pm-essentials skipped)
   WARN 2 plugin(s) were skipped: ['pm-essentials', 'nutri']. Reinstall after upgrading.
   === VERIFICATION PASSED ===
   ```

2. **Plugin data is preserved in SQLite** — the source database is never
   modified.  No plugin data is lost; it just hasn't been migrated yet.

3. **Upgrade the plugin** in its external repository by adding
   `migrations/install.postgres.sql` (and `uninstall.postgres.sql`).  See the
   translation reference above.

4. **Reinstall on the PG-backed instance:**

   ```bash
   # With the PG instance running (DATABASE_URL pointing to Postgres)
   make plugin-update PLUGIN=pm-essentials
   ```

   This runs `install.postgres.sql`, creating the plugin tables on Postgres.

5. **Import plugin data manually if needed.**  If you need to carry existing
   plugin rows (e.g. `pm_essentials_projects`) from SQLite to the now-created
   PG tables, you can re-run the migrate tool targeting only those tables
   (future: `--only-tables` flag) or export/import via CSV.

### Limitations

- Plugin-specific data is **not automatically migrated** when using
  `--skip-incompatible-plugins`.  Only the `plugins_installed` registry row
  is carried over.
- If the plugin stores critical business data (e.g. `nutri` patient records),
  plan the data import step before running in production.

---

## Questions?

Open an issue at https://github.com/EvolutionAPI/evonexus or reference ADR
`docs/architecture.md §PG-Q7` for the authoritative decision record.
