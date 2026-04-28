# EvoNexus Plugin Contract

This is the canonical reference for EvoNexus plugins shipping with **EvoNexus 1.0**.
It documents the `plugin.yaml` manifest, the auxiliary YAML files (`heartbeats.yaml`,
`routines.yaml`), the host endpoints a plugin can call at runtime, and the
filesystem layout the installer expects.

For a working end-to-end example to clone, the **`evo-essentials`** plugin
covers one of every capability:
[github.com/EvolutionAPI/evonexus-plugin-evo-essentials](https://github.com/EvolutionAPI/evonexus-plugin-evo-essentials).

---

## 1. Plugin folder layout

```
my-plugin/
├── plugin.yaml                 # required — manifest
├── heartbeats.yaml             # optional — proactive agent declarations
├── routines.yaml               # optional — scheduled scripts
├── migrations/
│   ├── install.sqlite.sql      # required if capabilities: [sql_migrations]
│   ├── install.postgres.sql    # required if capabilities: [sql_migrations]
│   ├── uninstall.sqlite.sql    # required if you ship install.*
│   └── uninstall.postgres.sql
├── agents/<name>.md            # one .md per agent (YAML frontmatter required)
├── skills/<name>.md            # one .md per skill (YAML frontmatter required)
├── rules/<name>.md             # one .md per rule (free-form markdown)
├── hooks/<file>.py             # claude_hooks handler scripts
├── scripts/<file>.py           # routine scripts
├── src/                        # TypeScript / TSX source for ui_pages and widgets
├── dist/                       # built ESM bundles (committed; host serves them)
│   └── pages/<id>.js
└── ui/widgets/<filename>.js    # built widget bundles (committed)
```

The installer copies the whole folder into `plugins/<slug>/` on the host.
**Do not rely on `node_modules` on the host** — anything you need at runtime
must end up in `dist/` or `ui/widgets/` and be committed.

---

## 2. `plugin.yaml` — top-level fields

```yaml
schema_version: "2.0"           # required; literal string. Validated on install.
id: my-plugin                   # required; ^[a-z][a-z0-9-]{1,62}[a-z0-9]$
name: My Plugin                 # required; human-readable, max 200 chars
version: 1.0.0                  # required; valid semver
description: >
  One paragraph describing what the plugin does and the domain it covers.
author: "Your Name <you@example.com>"
license: MIT
homepage: https://github.com/you/my-plugin    # optional
min_evonexus_version: 0.34.0    # required; semver. Install fails if host < this.
tier: essential                 # required; only "essential" supported in 1.0

capabilities:                   # explicit allowlist; see §3
  - agents
  - skills
  - rules
  - sql_migrations
  - ui_pages
  - widgets
  - readonly_data
  - writable_data
  - claude_hooks
  - heartbeats
```

> A capability **must** be in `capabilities:` before the corresponding block
> is allowed. Unknown capabilities are rejected at install time. Empty blocks
> for declared capabilities are tolerated.

### Identity rules

- `id` is the canonical slug. It is used as the plugin folder name, as the
  prefix for namespaced agents/skills/rules (`plugin-<id>-*`), and as the
  required prefix for any SQL table the plugin creates (`<id_underscored>_*`).
- `id` and `version` together form the install key — you cannot install two
  plugins with the same `id`, and reinstalling the same version is a no-op.

---

## 3. Capabilities reference

| Capability       | Where it lives                       | Purpose                                             |
| ---------------- | ------------------------------------ | --------------------------------------------------- |
| `agents`         | `plugin.yaml` `agents:` + `agents/`  | Markdown agents with YAML frontmatter               |
| `skills`         | `plugin.yaml` `skills:` + `skills/`  | Slash-command skills with YAML frontmatter          |
| `rules`          | `plugin.yaml` `rules:` + `rules/`    | Operational rules injected into agent prompts       |
| `claude_hooks`   | `plugin.yaml` `claude_hooks:`        | PreToolUse/PostToolUse/Stop/SubagentStop handlers   |
| `widgets`        | `ui_entry_points.widgets`            | Web-component widgets mounted on host pages         |
| `ui_pages`       | `ui_entry_points.pages`              | Full-screen React pages routed under `/plugins-ui/` |
| `writable_data`  | `plugin.yaml` `writable_data:`       | Tables exposed for POST/PUT/DELETE via host API     |
| `readonly_data`  | `plugin.yaml` `readonly_data:`       | Named SELECT queries exposed via host API           |
| `sql_migrations` | `migrations/install.{dialect}.sql`   | Schema setup at install / teardown at uninstall     |
| `heartbeats`     | `heartbeats.yaml` (separate file)    | Proactive agents on a schedule                      |
| `public_pages`   | `plugin.yaml` `public_pages:`        | Token-bound public pages served by host             |
| `safe_uninstall` | `plugin.yaml` `safe_uninstall:`      | 3-step uninstall wizard with data preservation      |
| `mcp_servers`    | `plugin.yaml` `mcp_servers:`         | MCP servers injected into `~/.claude.json`          |
| `integrations`   | `plugin.yaml` `integrations:`        | Named env-var bundles + optional health check       |
| `goals`          | `goals.yaml` (host-managed cascade)  | Seed Mission/Project/Goal rows tagged with plugin   |
| `tasks`          | `goals.yaml`                         | Seed `goal_tasks` rows tagged with plugin           |
| `triggers`       | reserved                             | Reserved for future contract                        |

> `routines.yaml` does **not** require a capability declaration — the installer
> imports any `routines.yaml` it finds. If you ship one, document it under
> Conventions (§14) so users know it exists.

---

## 4. `agents:` — markdown agent registration

```yaml
agents:
  - name: notes-agent
    file: agents/notes-agent.md
```

`file` is required (validated by schema). `name` is optional but recommended;
when present it is the label that shows up in the plugin's Capabilities panel.

Each `agents/<name>.md` file **must** start with YAML frontmatter:

```markdown
---
name: "notes-agent"
description: "Use this agent when the user wants to capture, organize..."
model: sonnet
color: green
memory: project
---

# Notes Agent
...
```

Agents are installed at `.claude/agents/plugin-<plugin_id>-<name>.md`.
The `plugin-<id>-` prefix is automatic — do **not** include it in the `name`
inside the frontmatter.

---

## 5. `skills:` and `rules:` — capability listings

```yaml
skills:
  - name: create-note
    src: skills/create-note.md

rules:
  - name: notes-conventions
    src: rules/notes-conventions.md
```

Both arrays use the same shape: `{name, src}`. `src` must be a relative path
inside the plugin folder (no `..`, no leading `/`).

- **Skills** are markdown files with frontmatter (same shape as native
  `.claude/skills/`). They become callable slash commands prefixed
  `plugin-<id>-<name>`.
- **Rules** are free-form markdown injected into agent prompts. They are the
  place to encode operational conventions (see `evo-essentials/rules/notes-conventions.md`
  for the canonical example).

> **Why both `name` and `src`?** The host persists both so the frontend can
> render the human label without re-parsing files, and the installer can
> locate the file on disk without trusting the label.

---

## 6. `claude_hooks:` — Claude Code event handlers

```yaml
claude_hooks:
  - event: PostToolUse
    handler_path: hooks/log-tool-use.py
```

Allowed events: `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`.
`handler_path` must be a relative path inside the plugin (no `..`, no absolute).
The handler receives the event payload as JSON on stdin and is expected to
exit 0 on success.

The reference plugin ships a working PostToolUse handler at
[`hooks/log-tool-use.py`](https://github.com/EvolutionAPI/evonexus-plugin-evo-essentials/blob/main/hooks/log-tool-use.py)
that appends a line to `plugins/<id>/.runtime/tool-use.log`.

---

## 7. `ui_entry_points` — pages, sidebar groups, widgets

```yaml
ui_entry_points:
  pages:
    - id: notes
      label: Notes
      path: notes                       # sub-path under /plugins-ui/<id>/
      bundle: dist/pages/notes.js       # ESM module with default export
      sidebar_group: essentials-group   # MUST match an id in sidebar_groups below
      icon: StickyNote                  # optional Lucide icon name
      order: 1

  sidebar_groups:
    - id: essentials-group
      label: Essentials
      order: 10
      collapsible: true

  widgets:
    - id: pinned-notes
      label: Pinned Notes
      filename: pinned-notes.js
      custom_element_name: my-plugin-pinned-notes
      mount_point: overview
```

### Pages — three rules that bite

1. **`sidebar_group` is required for the page to appear in the sidebar.** The
   host filters with strict equality (`page.sidebar_group === group.id`). A
   page without it persists but never renders a sidebar entry.
2. **`bundle` must be a pre-built ESM module with a default export of a React
   component**, e.g. `export default function NotesPage(...)`. Use `vite build
   --lib` (see §15 for the config).
3. **The host externalises React** — your bundle should declare `react` as
   external and rely on `window.React`. Do **not** bundle React itself.

### Widgets

Widgets are web components (custom elements). The installer copies
`ui/widgets/*.js` into `plugins/<id>/ui/widgets/` and serves them at
`/plugins/<id>/ui/widgets/<filename>?v=<version>`. The version query string is
added by the host on every reinstall to defeat the `Cache-Control: immutable`
header that would otherwise pin the old bundle for an hour.

The bundle must register the custom element under the name declared in
`custom_element_name`:

```ts
customElements.get(TAG) || customElements.define(TAG, MyWidget)
```

`mount_point` selects where the host renders it; `overview` is the only
mount point in 1.0.

---

## 8. `writable_data:` — POST/PUT/DELETE on plugin tables

```yaml
writable_data:
  - id: notes
    description: Personal notes with title, body, priority, pinned, due_date.
    table: my_plugin_notes              # MUST be prefixed with id_underscored_
    allowed_columns:
      - title
      - body
      - priority
      - pinned
      - due_date
    json_schema:
      type: object
      properties:
        title:    { type: string, minLength: 1, maxLength: 200 }
        priority: { type: string, enum: [low, medium, high] }
        pinned:   { type: boolean }
        due_date: { type: string, format: date }
      required: [title, priority]
```

### Endpoint

```
POST   /api/plugins/<id>/data/<resource_id>          # insert
PUT    /api/plugins/<id>/data/<resource_id>          # update (body must include `id`)
DELETE /api/plugins/<id>/data/<resource_id>?id=<row_id>
```

### Guarantees

- Only columns in `allowed_columns` are written; the rest are silently dropped.
- The `table` name is re-validated against the `<id>_` prefix at runtime.
- All values are sent as bind parameters — zero string interpolation.
- If `json_schema` is declared, the body is validated against it before the
  SQL runs (400 on failure, with the validation message in the response).

> **There is no GET on `/data/<resource_id>` in 1.0.** To list rows, declare
> a `readonly_data` query and call that endpoint instead. This trips up almost
> every new plugin author — the canonical fix is in §9.

---

## 9. `readonly_data:` — named SELECT queries

```yaml
readonly_data:
  - id: pinned_notes_count
    description: Count of pinned notes for the home widget.
    sql: >
      SELECT COUNT(*) AS count FROM my_plugin_notes WHERE pinned = TRUE
  - id: notes_all
    description: All notes ordered by priority (high first) and recency.
    sql: >
      SELECT id, title, body, priority, pinned, due_date, created_at
      FROM my_plugin_notes
      ORDER BY
        CASE priority WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC,
        created_at DESC
```

### Endpoint

```
GET /api/plugins/<id>/readonly-data/<query_id>
```

Note the **dash**: `readonly-data`, not `readonly_data`. Hitting `/data/<id>`
with GET returns 404 because that route only accepts mutating methods.

### Constraints

- `sql` must start with `SELECT` (the validator rejects INSERT/UPDATE/DELETE/DROP/
  CREATE/ALTER/ATTACH).
- Hard cap: 1000 rows per response.
- Available bind parameters: anything you declare in `params:` plus the
  reserved server-injected `:current_user_id` and `:current_user_role`.
- Boolean columns should be compared with `TRUE` / `FALSE`, not `1` / `0` —
  Postgres rejects implicit integer-to-boolean cast.

### Linking a query to a public page

```yaml
readonly_data:
  - id: order_summary
    description: Public-portal view of an order.
    sql: SELECT id, status, total FROM my_plugin_orders WHERE id = :order_id
    public_via: orders          # references a public_pages[].id
    bind_token_param: order_id  # parameter name that receives the URL token
```

---

## 10. `sql_migrations` — `install.<dialect>.sql` / `uninstall.<dialect>.sql`

EvoNexus 1.0 supports both SQLite and Postgres in a single deployment. Plugins
that touch the database must ship **both** dialect variants:

```
migrations/
├── install.sqlite.sql
├── install.postgres.sql
├── uninstall.sqlite.sql
└── uninstall.postgres.sql
```

The installer picks the file matching the active dialect at runtime. If only
one dialect is shipped, install fails on the other dialect with a clear error.

### What you can do

- Create tables prefixed with `<id_underscored>_` (e.g. `my_plugin_notes`).
- Create indexes, views, triggers, and (Postgres-only) functions.
- Reference host tables read-only via foreign keys. Do **not** modify them.

### What is forbidden

- `DROP TABLE` on anything outside your prefix (security scanner blocks).
- Writing to host tables (`users`, `agents`, `goals`, …).
- `ATTACH DATABASE` (SQLite) or cross-database queries (Postgres).
- Encoding secrets in the SQL.

---

## 11. `heartbeats.yaml` — proactive agents (separate file)

Heartbeats live in **`heartbeats.yaml` at the plugin root**, not in `plugin.yaml`.
They are imported into the host `heartbeats` table on install with
`source_plugin = <id>` and **default to disabled**. The user must explicitly
enable each one in `/scheduler`.

```yaml
heartbeats:
  - id: notes-priority-watch
    agent: notes-agent              # automatically prefixed with plugin-<id>- on install
    interval_seconds: 21600         # 6h
    max_turns: 5
    timeout_seconds: 300
    lock_timeout_seconds: 1800
    wake_triggers: [interval, manual]
    required_secrets: []
    decision_prompt: |
      Check my_plugin_notes for high-priority notes with no due_date.
      For each, suggest a due_date based on the title. If you find none, skip.
```

The host enforces the 9-step heartbeat protocol described in
[`heartbeats.md`](heartbeats.md). Plugin heartbeats use the same machinery as
host-defined ones.

---

## 12. `routines.yaml` — scheduled scripts (separate file)

```yaml
daily:
  - name: notes-cleanup
    script: scripts/notes_cleanup.py     # relative to plugin folder
    time: "21:30"
    agent: notes-agent

weekly:
  - name: notes-weekly-digest
    script: scripts/notes_digest.py
    day: monday
    time: "09:00"

monthly:
  - name: notes-monthly-archive
    script: scripts/notes_archive.py
    day: 1
```

Routines are imported into `routine_definitions` with `source_plugin = <id>`
and **default to disabled**. The host scheduler runs them via `make scheduler`.

The script receives `EVONEXUS_HOME` in the environment and can use
`from sdk_client import evo` to call the host API. See
[`scripts/notes_cleanup.py`](https://github.com/EvolutionAPI/evonexus-plugin-evo-essentials/blob/main/scripts/notes_cleanup.py)
in the reference plugin.

---

## 13. `mcp_servers:` and `integrations:`

### MCP servers

```yaml
mcp_servers:
  - name: notes-fs
    command: npx                        # one of: npx node python python3 uv uvx deno
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "${PLUGIN_DIR}"
    env: {}
```

Effective name in `~/.claude.json` is `plugin-<id>-<name>`. Supported
interpolations in `args` and `env` values:

- `${WORKSPACE}` — absolute path to the EvoNexus workspace
- `${PLUGIN_DIR}` — absolute path to `plugins/<id>/`
- `${ENV:VAR_NAME}` — value of `VAR_NAME` from `.env` (install fails if absent)

Shell metacharacters (`;&|<>\``) are rejected at install time.

### Integrations

```yaml
integrations:
  - slug: notes-export
    label: Notes Export Webhook
    category: productivity              # one of: erp payments crm messaging community social productivity meetings creative other
    env_vars:
      - name: NOTES_EXPORT_WEBHOOK_URL
        description: Webhook called whenever a high-priority note is created.
        required: false
        secret: false
      - name: NOTES_EXPORT_API_KEY
        description: Bearer token for the webhook above.
        required: false
        secret: true
    health_check:                       # optional
      type: http
      url: "${NOTES_EXPORT_WEBHOOK_URL}/health"
      expect_status: 200
      timeout_seconds: 5
```

Env var names must be uppercase. The host writes them to `.env` (never DB).
Secret values are masked in the UI. `health_check.url` may only reference env
vars declared in the same integration (anti-exfiltration guard).

---

## 14. `public_pages:` — token-bound public pages

Requires `capabilities: [public_pages]`.

```yaml
public_pages:
  - id: orders
    description: Customer-facing order tracking page.
    route_prefix: orders
    token_source:
      table: my_plugin_orders           # must start with id_underscored_
      column: access_token
    bundle: ui/public/orders.js         # must start with ui/public/
    custom_element_name: my-plugin-orders
    auth_mode: token                    # only "token" supported in 1.0
    rate_limit_per_ip: "60/minute"
    audit_action: order_view
```

### Routes

| Method | Path                                              | Description                            |
| ------ | ------------------------------------------------- | -------------------------------------- |
| GET    | `/p/<id>/<prefix>/<token>`                        | HTML bundle (portal entry)             |
| GET    | `/p/<id>/<prefix>/<token>/data`                   | Run a `public_via`-tagged query        |
| GET    | `/p/<id>/<prefix>/<token>/public-assets/<path>`   | Static assets from `ui/public/`        |

All three:
1. Validate the token parametrically against `token_source.table.column`.
2. Apply rate limiting (60/min on portal, 120/min on data).
3. Emit security headers (CSP, X-Content-Type-Options, Referrer-Policy, HSTS).
4. Write an audit log entry tagged with `audit_action`.

---

## 15. `safe_uninstall:` — 3-step uninstall wizard

Requires `capabilities: [safe_uninstall]`.

```yaml
safe_uninstall:
  enabled: true
  block_uninstall: false                # if true, uninstall always returns 409
  reason: >
    LGPD requires a 30-day grace period before patient records can be
    permanently deleted. The wizard exports + preserves data first.

  user_confirmation:
    checkbox_label: "Eu confirmo que tenho permissão para desinstalar este plugin."
    typed_phrase: "APAGAR PLUGIN my-plugin"

  pre_uninstall_hook:
    script: scripts/export.py
    output_dir: exports
    timeout_seconds: 300
    must_produce_file: true

  preserved_tables:                     # renamed to _orphan_<id>_<table> instead of dropped
    - my_plugin_patients
    - my_plugin_records

  preserved_host_entities:              # partial-row preservation in host tables
    audit_log: "actor_user_id IS NOT NULL"
```

### Host enforcement when `enabled: true`

1. **Admin role required** (non-admin → 403).
2. **Confirmation phrase** must match `typed_phrase` exactly.
3. **Export verification** — `exported_at` path must be present and the file
   must exist before the uninstall proceeds.
4. **ZIP password** must be present (forwarded to the pre-uninstall hook).
5. **Pre-uninstall hook** runs in a sandboxed subprocess with no secrets in
   the environment (only `PLUGIN_SLUG`, `PLUGIN_VERSION`, `OUTPUT_DIR`,
   `DB_READONLY_PATH`). Non-zero exit aborts.
6. **Preserved tables** are renamed to `_orphan_<id>_<table>` and recorded in
   `plugin_orphans`. They are **never dropped**.
7. **Cascade-DELETE filtering** — for `preserved_host_entities`, only rows
   NOT matching the preservation predicate are deleted.

### Force-uninstall escape hatch

`EVONEXUS_ALLOW_FORCE_UNINSTALL=1` in the host env bypasses every check.
Every force-uninstall logs `plugin_uninstall_force` in the audit table with
the acting user's identity. Emergency recovery only.

### Reinstall after safe_uninstall

On reinstall of a plugin with orphaned tables:

1. Host checks `plugin_orphans` for unrecovered rows.
2. Compares `tarball_sha256` of the incoming bundle against `original_sha256`
   recorded at uninstall.
3. SHA256 mismatch → install blocked unless the request includes
   `confirmed_sha256_change: true`.
4. On match (or explicit override) the orphan tables are renamed back
   (`_orphan_<id>_<table>` → `<table>`) **before** `install.sql` runs.

---

## 16. Bundling for the browser (`vite.config.ts`)

The most common build mistake is shipping a bundle the browser can't run.
Two rules:

### Library mode does not auto-replace `process.env.NODE_ENV`

App builds replace `process.env.NODE_ENV` automatically; library builds do
not. Without an explicit `define`, your bundle ships raw `process.env`
references and crashes the browser with `process is not defined` the moment
React tries to mount.

```ts
// vite.config.ts
export default defineConfig({
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
    'process.env': '{}',
  },
  plugins: [react({ jsxRuntime: 'classic' })],
  build: {
    lib: {
      entry: { 'pages/notes': 'src/pages/notes.tsx' },
      formats: ['es'],
    },
    rollupOptions: {
      external: ['react'],                  // host supplies window.React
      output: {
        entryFileNames: '[name].js',
        globals: { react: 'React' },
      },
    },
    sourcemap: true,
  },
})
```

### Don't depend on host React contexts you don't own

The host's `ToastProvider` is **not** the same as `@evoapi/evonexus-ui`'s
`ToastProvider`. Importing `useToast` from the lib without wrapping your page
in the lib's own provider crashes with `useToast must be used within
<ToastProvider>`. Either wrap your page yourself or skip the toast hook
entirely (the reference plugin uses `console.log`).

---

## 17. Conventions and gotchas

- **Always supply `credentials: 'include'`** on `fetch` calls from page bundles
  and widgets — the host uses cookie auth and the bundle is served same-origin.
- **All identifiers in plugin SQL are validated** against `^[a-z][a-z0-9_]*$`
  at install time. The host never interpolates untrusted input into SQL identifiers.
- **Boolean columns** must be compared with `TRUE` / `FALSE`. `WHERE pinned = 1`
  works on SQLite but throws on Postgres.
- **Pre-uninstall hooks** run with a read-only DB copy. No write access. No
  secret env vars.
- **Rate limits** apply at the IP level on every public endpoint.

---

## 18. Reference plugin

The `evo-essentials` plugin is the canonical reference implementation. It
exercises every capability in this document with the smallest viable example:

[github.com/EvolutionAPI/evonexus-plugin-evo-essentials](https://github.com/EvolutionAPI/evonexus-plugin-evo-essentials)

When in doubt, copy from there.

---

## 19. Changelog

| Version | Change                                                                   |
| ------- | ------------------------------------------------------------------------ |
| 1.0     | First public Plugin Contract. Schema string `schema_version: "2.0"`.     |
|         | Capabilities: agents, skills, rules, claude_hooks, widgets, ui_pages,    |
|         | writable_data, readonly_data, sql_migrations, heartbeats, public_pages,  |
|         | safe_uninstall, mcp_servers, integrations, goals, tasks, triggers.       |
