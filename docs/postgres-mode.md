# Postgres Mode

EvoNexus runs on **SQLite by default** (file-based, zero-config) or **PostgreSQL**
(robust, multi-process, native backups). In Postgres mode, **all configuration
lives in the database** — no YAML/JSON files are read at runtime for workspace
state, providers, heartbeats, or routines.

---

## When to use Postgres

Pick PG when you need any of:

- **Native backups** via `pg_dump` (covers configs + data + audit log).
- **Remote access** to data (BI, exports, multi-machine setup).
- **Multiple workers** (gunicorn) without file-locking issues.
- **Operational visibility** — change history flows through `audit_log`.

SQLite is recommended for single-machine personal use. Configs in YAML stay
git-friendly; everything just works without a server.

---

## Quick start (fresh install)

```bash
# 1. Create the database (Supabase, Neon, or self-hosted)
export DATABASE_URL=postgresql://user:password@host:5432/evonexus

# 2. Apply schema
make db-upgrade

# 3. Run setup wizard — writes configs directly to DB (no YAML created)
make setup

# 4. Start the dashboard
make dashboard-app
```

---

## Migration from SQLite

If you already run EvoNexus on SQLite and want to move to PG:

```bash
# 1. Backup your SQLite DB just in case
cp dashboard/data/evonexus.db dashboard/data/evonexus.db.bak

# 2. Point EvoNexus at PG
export DATABASE_URL=postgresql://user:password@host:5432/evonexus

# 3. Apply the schema
make db-upgrade

# 4. Copy data from SQLite to PG (idempotent, --dry-run available)
make db-migrate \
  SOURCE=sqlite:///dashboard/data/evonexus.db \
  TARGET=$DATABASE_URL

# 5. Copy file-based configs (workspace.yaml, providers.json, heartbeats.yaml,
#    routines.yaml, plugins/*/heartbeats.yaml, plugins/*/routines.yaml) to DB
make import-configs
```

After step 5, the file configs become inert in PG mode — the app reads
exclusively from the database.

If a plugin in your SQLite workspace doesn't yet support PG (no
`install.postgres.sql`), use `make db-migrate-skip-plugins` instead.

---

## Configuration sources

| Subsystem  | SQLite mode             | Postgres mode               |
|-----------|-------------------------|------------------------------|
| Workspace  | `config/workspace.yaml`  | `runtime_configs` table      |
| Providers  | `config/providers.json`  | `llm_providers` + `runtime_configs.active_provider` |
| Heartbeats | `config/heartbeats.yaml` | `heartbeats` table            |
| Routines   | `config/routines.yaml`   | `routine_definitions` table   |
| Plugin hb  | `plugins/*/heartbeats.yaml` (glob at runtime) | `heartbeats` table tagged `source_plugin=<slug>` |
| Plugin rt  | `plugins/*/routines.yaml` (glob at runtime)   | `routine_definitions` table tagged `source_plugin=<slug>` |
| Port       | `EVONEXUS_PORT` env (fallback to YAML)        | `EVONEXUS_PORT` env only      |

The single seam that bifurcates is `dashboard/backend/config_store.py` (and the
sister modules `provider_store.py`, `routine_store.py`). All read/write of
configs goes through these helpers — adding a new place that reads YAML
directly will fail the `greplint pg-native-configs` CI job.

---

## Hot reload

Both modes support live-reload of heartbeats and routines without restarting:

- **SQLite**: writes update the YAML; loaders relé at next dispatch.
- **Postgres**: triggers on `heartbeats` and `routine_definitions` issue
  `pg_notify('config_changed', ...)`. The dispatcher and scheduler each open
  a dedicated connection running `LISTEN config_changed` and reload on
  notification (typically <1s end-to-end).

There is currently no SSE/WebSocket push to the **frontend** — opening
Settings while another admin is editing in PG mode requires a manual refresh
to see their change. (Tracked as a follow-up.)

---

## Connection pooling (Postgres only)

Defaults are tuned for self-hosted PG with capacity:

| Variable                       | Default | Notes                              |
|--------------------------------|--------:|------------------------------------|
| `EVONEXUS_DB_POOL_SIZE`        | 5       | Per-process pool size              |
| `EVONEXUS_DB_MAX_OVERFLOW`     | 10      | Burst above pool_size              |

Each gunicorn worker holds its own pool. Plus the scheduler and heartbeat
dispatcher each hold one dedicated `LISTEN` connection. For free-tier hosts
(Supabase free, Neon free) reduce the defaults:

```bash
export EVONEXUS_DB_POOL_SIZE=3
export EVONEXUS_DB_MAX_OVERFLOW=5
```

The boot path checks `processes × (pool_size + max_overflow)` against the
provider's `max_connections` and warns at >70%, fail-fast at 100%.

---

## Plugin contract in PG mode

Plugin install (`plugins/<name>/heartbeats.yaml` or `routines.yaml` present):

1. Plugin SQL applied to PG (the plugin must ship `install.postgres.sql`).
2. Heartbeats and routines from the plugin's YAML files are imported with
   `source_plugin=<slug>` set.
3. Trigger fires `pg_notify`; dispatcher and scheduler reload.

Plugin uninstall:

1. `DELETE FROM heartbeats WHERE source_plugin = <slug>` — user-defined
   heartbeats (with `source_plugin IS NULL`) are untouched.
2. Same for `routine_definitions`.

Plugin update:

1. Snapshot current `enabled` state from `heartbeats WHERE source_plugin = <slug>`.
2. `DELETE` + re-`INSERT` from the new YAML in a single transaction.
3. `enabled` is restored from the snapshot — toggling a plugin heartbeat off
   is preserved across upgrades.

---

## Backup & restore

In Postgres mode, `make backup` (or `python backup.py backup`) automatically
embeds a `pg_dump --format=custom` of your database inside the ZIP as
`database.dump`. The ZIP also captures workspace files, memory, and plugins
as in SQLite mode.

Requirements: `pg_dump` and `pg_restore` must be in `PATH`. On macOS install
via Homebrew (`brew install postgresql`); on Linux use the distro's
`postgresql-client` package.

Restore picks up the dump automatically when `DATABASE_URL` points to PG:

```bash
DATABASE_URL=postgresql://... python backup.py restore <file.zip> --mode merge
# or --mode replace to drop existing schema first (--clean --if-exists)
```

Backend mismatches abort with a clear error — you cannot restore a Postgres
ZIP onto a SQLite host or vice versa. Use `evonexus-migrate` for cross-backend
data migration instead.

The manifest records `db_backend: postgres` and `db_dump` metadata (size,
format, options) so you can inspect a ZIP before restoring.

---

## Known limitations

These are deferred to follow-up work — none of them block production use:

- **Frontend cache invalidation**: backend caches invalidate via NOTIFY, but
  the React frontend has its own state. Multi-admin edits may show stale
  values in unrelated browser tabs until reload.
- **LISTEN connection budget**: each long-running process opens one dedicated
  PG connection. On free-tier hosts (60-100 max conns), tune `EVONEXUS_DB_POOL_SIZE`
  down or run fewer gunicorn workers. A single multiplexer process is on the
  roadmap to consolidate this.
- **Smart-router**: still file-based (`config/smart-router.json`). Out of
  scope for the current milestone.

---

## Troubleshooting

### `make db-migrate` fails with `Plugin X does not support PostgreSQL`

The plugin still ships only `install.sqlite.sql`. Either:

- Ship `install.postgres.sql` alongside the SQLite file — see
  [plugin-contract.md §10](./plugin-contract.md).
- Run `make db-migrate-skip-plugins` to migrate core data without the plugin's
  schema/data; reinstall the plugin in PG when an updated version is available.

### `make import-configs` reports divergence

DB and YAML disagree on a value. By default the CLI skips with a warning to
prevent silent overwrite. Either:

- Decide YAML wins → `make import-configs ARGS="--force"`.
- Decide DB wins → edit the YAML to match (or delete/comment the entry).

### Heartbeats don't reload after editing in the UI

Confirm the trigger is active:

```sql
SELECT trigger_name FROM information_schema.triggers
WHERE event_object_table = 'heartbeats';
-- Expected: trg_heartbeats_notify
```

If missing, re-run `make db-upgrade` to apply migration `0008`.

### Schema is out of sync with the ORM

Run the audit script:

```bash
DATABASE_URL=postgresql://... uv run python scripts/audit_schema_drift.py
```

Any drift other than `DATETIME` vs `TIMESTAMP` (cosmetic) means a migration is
missing. File an issue with the output.
