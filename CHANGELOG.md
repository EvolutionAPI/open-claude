# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.15.1] - 2026-04-11

### Changed

- **Brand refresh — new EvoNexus logo** — `public/EVO_NEXUS.png` is now the canonical brand asset. `public/cover.svg` has the old `<text>Evo Nexus</text>` replaced by an embedded base64 `<image>` of the new logo, so the README banner renders the real brand mark in any viewer without external dependencies. Copies of `EVO_NEXUS.png` also live at `site/public/assets/EVO_NEXUS.png` and `dashboard/frontend/public/EVO_NEXUS.png` so the site and dashboard can serve it directly.
- **`site/src/pages/Home.tsx` — nav header** — the top navigation now shows only the EvoNexus PNG logo (`@assets/EVO_NEXUS.png`). The legacy Evolution logo (`@assets/logo.png`) and the duplicate `<span>Evo</span><span>Nexus</span>` text that sat next to it were both removed from the header — Evolution branding remains on the case-study card and the footer where it belongs.
- **`dashboard/frontend/src/components/Sidebar.tsx` — sidebar header** — the two-tone `<h1><span>Evo</span><span>Nexus</span></h1>` heading was replaced by `<img src="/EVO_NEXUS.png" className="h-8 w-auto" />`, matching the new brand.
- **Skill count bumped to 150+ across every source of truth** — `README.md` (4 spots: intro bullet, Key Features list, dashboard table, folder tree), `public/cover.svg` (badge), `.claude/rules/skills.md` (header), `docs/introduction.md`, `docs/architecture.md` (ASCII diagram + evo-skills note), `docs/skills/overview.md`, `docs/getting-started.md`, and `site/src/pages/Home.tsx` (4 spots: hero paragraph, stat card, feature tile, "Skills as Instructions" description). Previous counts of `~137`, `~140`, `137+`, `~130` all normalized to `150+`. `docs/llms-full.txt` regenerated via `make docs-build` to pick up the new numbers.

## [0.15.0] - 2026-04-11

### Added

- **Learning Loop feature** — knowledge retention system based on SM-2 spaced repetition. Four skills: `learn-capture` (extract 1-5 atomic facts from pasted content), `learn-review` (run SM-2 sessions with Again/Hard/Good/Easy grades updating `interval`/`ease` in-place), `learn-quiz` (retrieval-practice question sets, read-only), `learn-stats` (total facts, overdue count, retention rate, active decks, facts added this week). Facts are individual markdown files in `workspace/learning/facts/` with full SM-2 frontmatter (`interval`, `ease`, `reps`, `lapses`, `next_review`). Review history appended to `.state/review-log.jsonl` for audit. All user data gitignored by default — only `workspace/learning/README.md` is committed. Pull-only in v0 (no Telegram push, no Fathom auto-capture — deferred).
- **`@lumen-learning` agent** — new business-layer agent (17th) dedicated to learning retention. Orchestrates the four `learn-*` skills and keeps separation of concerns clean: `@mentor-courses` creates learning content, `@lumen-learning` makes it stick. Command: `/lumen-learning`. Model: sonnet. Color: yellow.
- **`learning_weekly` routine** — scheduled for Sundays 09:45 BRT via `ADWs/routines/custom/learning_weekly.py`. Generates a markdown digest in `workspace/daily-logs/YYYY-MM-DD-learning-weekly.md` with overdue facts and retention stats. Read-only — never mutates SM-2 frontmatter. Makefile target: `make learn-weekly`.
- **Agent avatars in the dashboard** — 35 custom PNG avatars under `dashboard/frontend/public/avatar/` covering all business agents (12) and 19 engineering agents (helm, mirror also now included). New `AgentAvatar` component renders the PNG as a circular image when available, or falls back to a colored circle with the Lucide icon when not. Integrated into the agent list cards (`Agents.tsx`, 56px) and the agent detail page header (`AgentDetail.tsx`, 60px with colored halo).
- **Agent count bumped across all docs** — README, `docs/introduction.md`, `docs/agents/overview.md`, `docs/architecture.md`, `docs/real-world/evolution-foundation.md`, `docs/dashboard/overview.md`, `docs/guides/initial-setup-skill.md`, `site/src/pages/Home.tsx`, `.claude/rules/agents.md`, `CLAUDE.md` updated from 37 (16 business) → 38 (17 business). `public/cover.svg` text updated from `37 Agents` → `38 Agents`.

### Changed

- **`dashboard/frontend/src/lib/agent-meta.ts`** — expanded from 19 entries to 38. All 21 engineering agents were previously falling through to `DEFAULT_META` (generic `Bot` icon, no slash command badge); each now has a dedicated entry with icon, color, command, label, and avatar path. Business agents `aria-hr`, `zara-cs`, `lex-legal`, `nova-product`, `dex-data`, `helm-conductor`, `mirror-retro` also gained their `avatar` field. `AgentMeta` interface extended with optional `avatar?: string`.
- **`AgentDetail.tsx` header** — grew from `h-14` to `h-20` to accommodate the 60px avatar with its colored halo to the left of the agent name and command.

## [0.14.1] - 2026-04-11

### Fixed

- **`/api/overview` endpoint** — dropped from ~16s to ~29ms (≈500× faster). `_recent_reports` was rglob'ing the entire `workspace/` tree, which on an active install holds vendored third-party repos under `workspace/projects/` (mcp-dev-brasil, oh-my-claudecode, evoai-services, etc.) — 16.853 of 17.116 MD/HTML files (98.5%) lived there and had nothing to do with "recent reports". The scan now skips top-level `projects/` (vendored repos) and `meetings/` (raw Fathom transcripts), iterates remaining areas, and formats the `date` field from the actual `mtime` instead of `path.split("/")[-1][:10]` (which was returning garbage like `"README.md"`).
- **Site typecheck errors** — `site/src/pages/Home.tsx` had 3 lucide icons (`MessageSquare`, `GitBranch`, `Database`) passing an invalid `title` prop. Wrapped them in `<span title="...">` to keep the hover tooltip and pass `tsc --noEmit`.
- **Dashboard frontend build** — `dashboard/frontend/src/pages/Providers.tsx` was importing `type LucideIcon` without using it, which caused `make dashboard-app` to fail with `TS6133`. Unused import removed.
- **Terminal startup garbage (WIP, 2 attempts included)** — on starting any agent terminal from the dashboard, bytes like `0?1;2c` / `000000` / `^[[0^[[0...` showed up in the prompt and status bar. Root cause is xterm.js auto-replying to terminal queries (DA1 `\x1b[c`, DA2 `\x1b[>c`, DSR `\x1b[5n`/`\x1b[6n`, window ops `\x1b[...t`) via `term.onData`, which the frontend was forwarding to the pty as if it were keyboard input. This release ships two defensive layers — passing `cols`/`rows` upfront on `start_claude` so the pty is born at the right size, and registering CSI handlers via `term.parser.registerCsiHandler({ final: 'c' | 'n' | 't' }, () => true)` to intercept queries at the parser level — plus a regex filter on `onData` as a second line of defense. **The bug is not fully resolved in this release.** Some payloads still slip through (likely via a non-CSI `triggerDataEvent` path that hasn't been pinned down yet). A debug log was added to `AgentTerminal.tsx` to capture the exact bytes in the next iteration.

### Changed

- **Feature folder convention** — `workspace/features/{slug}/` is now `workspace/development/features/{slug}/` across all engineering layer prompts (`.claude/rules/dev-phases.md`, `.claude/agents/compass-planner.md`, `.claude/agents/helm-conductor.md`, `.claude/commands/helm-conductor.md`, `.claude/agents/mirror-retro.md`, `docs/agents/engineering-layer.md`). Keeps all engineering artifacts (features, plans, architecture, reviews, verifications, retros) grouped under one development/ root.

### Docs

- **Multi-provider documentation** — README, `docs/introduction.md`, `docs/getting-started.md`, `docs/reference/env-variables.md`, `docs/dashboard/overview.md` updated with the OpenClaude-based multi-provider story introduced in v0.14.0. New `docs/dashboard/providers.md` documents the Providers page (supported providers, activation flow, security model with CLI + env var allowlists, logout warning). Site landing page replaces the "Full Control" feature card with "Multi-Provider, No Lock-In" highlighting the new capability.

## [0.14.0] - 2026-04-10

### Added

- **`dashboard/terminal-server/`** — lean terminal bridge powering the dashboard's per-agent xterm session. Fork of `vultuk/claude-code-web` stripped down from ~3.500 lines / 158 npm packages to ~440 lines / 74 packages, keeping only what the dashboard consumes: `POST /api/sessions/for-agent`, `GET/DELETE /api/sessions/:id`, and a WebSocket with `join_session` / `start_claude` / `input` / `resize` / `ping` / `stop`. Removed codex & cursor bridges, usage analytics, auth, HTTPS, ngrok, PWA, folder browser, and the entire legacy web UI. Spawns the local `claude` CLI via `node-pty` and persists sessions to `~/.claude-code-web/sessions.json`. New Makefile targets `terminal-logs` / `terminal-stop`. A `postinstall` hook restores the `darwin-arm64`/`darwin-x64` `node-pty` `spawn-helper` executable bit so `posix_spawnp` doesn't fail on fresh installs.
- **`make bling-auth`** — one-shot OAuth2 bootstrap for the Bling integration. Runs `.claude/skills/int-bling/scripts/bling_auth.py` to capture the initial access + refresh tokens into `.env`; subsequent refreshes are automatic via the skill.
- **Docs** — new `docs/integrations/bling.md` and `docs/integrations/asaas.md` with endpoint coverage, auth setup, and example calls. `docs/integrations/overview.md` expanded with the two Brazilian integrations.
- **Frontend** — new `dashboard/frontend/src/lib/agent-meta.ts` centralizing the agent icon/color/command/label metadata used by `Agents.tsx`, `AgentDetail.tsx`, and the refreshed `AgentTerminal.tsx`.

### Changed

- **`int-bling` skill** — upgraded from manual v1 Bearer token to OAuth2 with automatic refresh. Access token expires in 6 hours; the skill now reads `BLING_CLIENT_ID` / `BLING_CLIENT_SECRET` / `BLING_REFRESH_TOKEN` from `.env` and refreshes on 401, persisting the new token pair back to disk. `.env.example` documents the new variables and points to `make bling-auth` for first-time setup.
- **`.claude/rules/integrations.md`** — Bling row updated to reflect OAuth2 auto-refresh + `make bling-auth`. Asaas row now mentions marketplace split.
- **`dashboard/frontend/src/App.tsx`, `pages/Agents.tsx`, `pages/AgentDetail.tsx`, `components/AgentTerminal.tsx`** — refactored to consume the new `agent-meta.ts` module and the leaner terminal-server endpoints. Error messages updated from `cc-web` → `terminal-server`.
- **`Makefile`** — `dashboard-app` target now boots `dashboard/terminal-server/bin/server.js --dev` instead of the old `claude-code-web/bin/cc-web.js`. Helper targets renamed `cc-web-logs` → `terminal-logs`, `cc-web-stop` → `terminal-stop`.
- **`.gitignore`** — ignores `dashboard/terminal-server/node_modules/` and its `package-lock.json`.

### Fixed

- **Terminal spawn failures on fresh installs** — `node-pty`'s `spawn-helper` prebuild was being extracted without the execute bit on macOS, causing `posix_spawnp failed` when the dashboard tried to start a claude session. Fixed by adding a `postinstall` script that re-applies `chmod +x` on both `darwin-arm64` and `darwin-x64` prebuilds.

## [0.13.3] - 2026-04-10

### Added

- **New skill `int-bling`** — Bling ERP API v3 integration. 10 operations across products (list/create), sales orders (list/create), contacts (list/create, F/J types), fiscal invoices/NF-e (list/create from orders), and stock (get/update by warehouse). Uses OAuth2 Bearer token (`BLING_ACCESS_TOKEN`). Schemas and endpoint coverage derived from the `mcp-dev-brasil` TypeScript reference implementation under `workspace/projects/mcp-dev-brasil/packages/erp/bling/`, complemented by [developer.bling.com.br](https://developer.bling.com.br) for advanced endpoints.
- **New skill `int-asaas`** — Asaas payment platform API v3 integration. 15 operations across payments (create/get/list, PIX QR code, boleto PDF), customers (create/list with CPF/CNPJ validation), subscriptions (create/list/cancel), financial (balance, transfer), marketplace (subaccount for split payments), and utilities (installments, webhook events). Uses `ASAAS_API_KEY` header auth with `ASAAS_SANDBOX=true` as safe default (sandbox.asaas.com), switchable to production. Enums documented: `billingType` (BOLETO/CREDIT_CARD/PIX/UNDEFINED) and payment `status` (PENDING/RECEIVED/CONFIRMED/OVERDUE/REFUNDED/etc). Schemas derived from `mcp-dev-brasil/packages/payments/asaas/` with Zod validation patterns ported to the skill.
- **`.env.example`** — new `BLING_ACCESS_TOKEN`, `ASAAS_API_KEY`, and `ASAAS_SANDBOX` entries under dedicated Brazilian ERP/payments sections.

### Changed

- **`.claude/rules/skills.md`** — `int-*` row bumped from 13 → 15, now listing Bling and Asaas alongside Stripe, Omie, and the other integrations.
- **README + docs** — skill counts updated: ~138 → ~140 total (~113 → ~115 business layer).

## [0.13.2] - 2026-04-10

### Added

- **New skill `prod-activation-plan`** — canonical pattern for producing phased activation plans: single index file at `workspace/development/plans/[C]{plan-name}-{date}.md` + one folder per phase (`fase-1-quick-wins/`, `fase-2-conexoes/`, `fase-3-ciclo-completo/`) + one file per item with a rich template (frontmatter, axis, type, concrete steps, decisions pending, impact, dependencies, risks, suggested agent team, status checklist). Includes agent routing rules for `[ATIVAR]` / `[DECIDIR]` / `[CONSTRUIR NOVO]` / `[EVOLUIR]` item types, and an expansion mode that preserves existing items while appending new ones with a version bump in the history section. Lives at `.claude/skills/prod-activation-plan/SKILL.md`.

### Changed

- **Oracle — Step 6 rewritten to use `prod-activation-plan`** — Oracle no longer invents plan structures on the fly. The canonical flow is now `Oracle (interview) → @compass-planner (content) → prod-activation-plan skill (structure) → Oracle (delivery)`. Added explicit `Step 6a` (delegate content to Compass), `Step 6b` (materialize via skill), and `Step 6c` (handle plan expansions preserving existing files). Oracle prompt now contains an explicit "NEVER invent your own plan structure" directive to prevent drift.
- **README + `docs/getting-started.md`** — Quick Start callout and Step 5 both point to `/oracle` as the first thing to run after installation, with the 7-step Oracle flow explained, the activation-plan structure documented, and the 3 autonomy paths (Guided / Autonomous / Delegated) surfaced. Skill counts bumped from ~137 → ~138 (prod-* subcategory grew from 9 → 10).
- **`.claude/rules/skills.md`** — `prod-*` row updated to include `activation-plan` in the inline list and count bumped to 10.

## [0.13.1] - 2026-04-10

### Fixed

- **Dashboard — delete social account now works** — the trash icon on `/integrations` was calling `POST /disconnect/{platform}/{index}`, a route that only exists in the standalone `social-auth` Flask app (port 8765), not in the dashboard backend (port 8080), so clicks silently 404'd. Added `DELETE /api/social-accounts/<platform>/<int:index>` to `dashboard/backend/app.py` reusing `env_manager.delete_account`, and updated `dashboard/frontend/src/pages/Integrations.tsx` to call `api.delete()` and consume the returned `{platforms}` payload in a single round-trip.
- **YouTube — automatic OAuth token refresh** — `SOCIAL_YOUTUBE_*_ACCESS_TOKEN` expires after ~1h, forcing a manual reconnect through social-auth. The `social-auth` OAuth flow already requested `access_type=offline` + `prompt=consent` and saved `REFRESH_TOKEN`, but `youtube_client.py` never used it. Added `_refresh_access_token(account)` that exchanges the refresh token at `https://oauth2.googleapis.com/token`, persists the new access token to `.env` (`SOCIAL_YOUTUBE_{N}_ACCESS_TOKEN`) and `os.environ`, and made `_api_get` auto-retry once on `HTTP 401` when a refresh token is available. Transparent to all callers (skills, routines, agents). Requires `YOUTUBE_OAUTH_CLIENT_ID` and `YOUTUBE_OAUTH_CLIENT_SECRET` in `.env` (already present for any OAuth-connected account).

## [0.13.0] - 2026-04-10

### Added

- **2 native engineering agents** — bringing the Engineering Layer to **21 agents** (19 derived from oh-my-claudecode + 2 native):
  - **`helm-conductor`** (sonnet, teal) — cycle orchestration agent. Sequences features, decides "what next?", routes tasks to phase owners, coordinates sprint planning. Does not do the work of any phase itself; it orchestrates.
  - **`mirror-retro`** (sonnet, silver) — blameless retrospective agent. Reads the full feature folder end-to-end at the close of a feature, sprint, or incident, and produces a structured retro with "what worked / didn't / surprises / lessons / proposed memory updates". Requires explicit user approval before writing to `memory/`.
- **Canonical 6-phase engineering workflow** — `.claude/rules/dev-phases.md` documents the EvoNexus development lifecycle: **Discovery → Planning → Solutioning → Build → Verify → Retro**. Each phase has an owner, inputs, outputs, exit criteria, and skip conditions. Includes handoff protocol, inherited-context rules, and a feature-skip matrix (typo fixes skip most phases; high-stakes migrations use all 6).
- **Feature folders as unit of work** — `workspace/features/{feature-slug}/` groups all artifacts of one feature (discovery, PRD, plan, architecture, reviews, verification, retro) in one coherent location. Coexists with the type-based folders in `workspace/development/{plans,reviews,...}/` which remain the canonical location for standalone artifacts.
- **Oracle redesigned as consulting entry point** — `@oracle` is now the official entry door to EvoNexus. It runs a full 8-step flow: detect workspace state → run `initial-setup` if needed → business discovery interview → delegate capability mapping to `@scout-explorer` → delegate gap analysis to `@echo-analyst` → present the "potential" in business language → delegate plan production to `@compass-planner` → deliver with 3 autonomy paths (guided / autonomous / delegated). Oracle keeps the relationship with the user in a single voice while orchestrating specialist agents for the heavy lifting. Prime directive: the user must never be left with doubts — check-ins are mandatory before any side-effect action and after every substantive response.

### Changed

- **`@compass-planner` now produces PRD + Plan in Phase 2** — for non-trivial feature work, Compass first produces `[C]prd-{feature}.md` (problem, goals, non-goals, user stories, acceptance criteria in Given/When/Then, constraints, open questions) and then derives `[C]plan-{feature}.md` from it. Trivial changes skip the PRD. Handoff chain updated: Compass → Apex (Phase 3) → Bolt (Phase 4), not directly Compass → Bolt for non-trivial work.
- **`README.md`, `CLAUDE.md`, `docs/introduction.md`, `docs/architecture.md`, `docs/agents/overview.md`, `docs/agents/engineering-layer.md`, `site/src/pages/Home.tsx`, `public/cover.svg`** — agent count updated from 35 → 37 (16 business + 21 engineering). Engineering layer descriptions mention the 2 native additions (Helm, Mirror) and the 6-phase workflow.
- **`.claude/rules/agents.md`** — Engineering Layer bumped to 21 agents. Helm and Mirror marked with ⭐ as EvoNexus-native (not derived from oh-my-claudecode). Header reference added to `.claude/rules/dev-phases.md` as the canonical workflow.
- **`docs/agents/engineering-layer.md`** — the "19 Agents" section is now "21 Agents", split into Reasoning (opus/sonnet, 8 agents — Mirror added), Execution (sonnet, 11 agents — Helm added), and Speed (haiku, 2 agents, unchanged). New section "The 6-Phase Workflow" documents the canonical pipeline with phase owners and feature-folder convention.
- **`dashboard/frontend/src/pages/Agents.tsx`** — `AGENT_META` now includes `helm-conductor` and `mirror-retro` with icons (`Navigation`, `History`), colors, labels, and slash commands. `ENGINEERING_TIERS` updated: Mirror added to `reasoning`, Helm added to `execution`.
- **`NOTICE.md`** — clarifies that 19 of 21 engineering agents are derived from OMC; Helm and Mirror plus `dev-phases.md` are native EvoNexus additions.

### Documentation

- New canonical workflow doc: `.claude/rules/dev-phases.md` (auto-loaded by engineering agents as they work).
- Updated `docs/llms-full.txt` (regenerated via `make docs-build`).

## [0.12.0] - 2026-04-10

### Added

- **Engineering Layer (19 agents)** — complete software development team derived from [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode) (MIT, by **Yeachan Heo**, v4.11.4). The layer is ortogonal to the existing Business Layer (16 agents). EvoNexus now ships with **35 specialized agents** in two layers + custom.
  - **Reasoning tier (opus, 7 agents):** `apex-architect`, `echo-analyst`, `compass-planner`, `raven-critic`, `lens-reviewer`, `zen-simplifier`, `vault-security`
  - **Execution tier (sonnet, 10 agents):** `bolt-executor`, `hawk-debugger`, `grid-tester`, `probe-qa`, `oath-verifier`, `trail-tracer`, `flow-git`, `scroll-docs`, `canvas-designer`, `prism-scientist`
  - **Speed tier (haiku, 2 agents):** `scout-explorer`, `quill-writer`
- **25 `dev-*` skills** organized in 3 tiers:
  - **Tier 1 — Core orchestration (15):** `dev-autopilot`, `dev-plan`, `dev-ralplan`, `dev-deep-interview`, `dev-deep-dive`, `dev-external-context`, `dev-trace`, `dev-verify`, `dev-ultraqa`, `dev-visual-verdict`, `dev-ai-slop-cleaner`, `dev-sciomc`, `dev-team`, `dev-ccg`, `dev-ralph`
  - **Tier 2 — Setup & infra (5):** `dev-mcp-setup`, `dev-deepinit`, `dev-project-session-manager`, `dev-configure-notifications`, `dev-release`
  - **Tier 3 — Meta utilities (5):** `dev-cancel`, `dev-remember`, `dev-ask`, `dev-learner`, `dev-skillify`
- **15 dev templates** in `.claude/templates/dev-*.md` — one per primary agent output: `dev-architecture-decision`, `dev-work-plan`, `dev-code-review`, `dev-bug-report`, `dev-verification-report`, `dev-deep-interview-spec`, `dev-security-audit`, `dev-test-strategy`, `dev-trace-report`, `dev-explore-report`, `dev-design-spec`, `dev-analysis-report`, `dev-research-brief`, `dev-critique`, `dev-simplification-report`.
- **`workspace/development/` folder** — engineering layer working directory with 7 subfolders (`architecture`, `plans`, `specs`, `reviews`, `debug`, `verifications`, `research`) and a `README.md`. Distinct from `workspace/projects/` (active git repos).
- **`NOTICE.md`** — third-party attribution for `oh-my-claudecode` with full MIT license, version pinned at v4.11.4, modifications listed (renaming, namespace `dev-*`, memory pattern adaptation, runtime stripping).
- **`docs/agents/engineering-layer.md`** — dedicated documentation page covering tiers, agents, pipelines, working folder, templates, memory pattern, cross-layer handoffs, and attribution.
- **Two-layer dashboard categorization** — `dashboard/frontend/src/pages/Agents.tsx` now categorizes agents into Business / Engineering (with reasoning/execution/speed tiers) / Custom, with auto-derived slash commands and dynamic icon assignment.

### Changed

- **Slash command naming** — all 35 core agents now use the **full agent name** as the slash command (e.g., `/clawdia-assistant`, `/flux-finance`, `/apex-architect`, `/bolt-executor`) instead of short aliases (`/clawdia`, `/flux`, `/apex`, `/bolt`). The only exception is `/oracle` which is already a single word. The 16 short business commands and the 13 short engineering commands were removed.
- **`README.md` updated** — agent count (16 → 35), skill count (~130 → ~137), Engineering Layer mention with attribution, two-layer description.
- **`CLAUDE.md` updated** — Active Projects table now lists "Engineering Layer" as delivered (v0.12.0). Folder Structure includes `workspace/development/`. "What Claude Should Do" rules cover both layers and link to NOTICE.md.
- **`docs/introduction.md`** — "35 specialized agents in two layers" framing, expanded "Chatbot vs EvoNexus" comparison table including engineering scenarios.
- **`docs/architecture.md`** — diagram refreshed to show 35 agents in two ortogonal layers, ~137 skills, attribution to Yeachan Heo.
- **`docs/agents/overview.md`** — Two-layer intro, 19 engineering agents grouped by tier, all 16 business agents updated with full slash commands.
- **`docs/skills/overview.md`** — engineering layer skills section with all 25 `dev-*` skills grouped by tier; total skill count updated to ~137.
- **`docs/agents/{16 individual}.md`** — slash commands updated to full names (e.g., `/clawdia` → `/clawdia-assistant`).
- **`site/src/pages/Home.tsx`** — `35 agents` / `137+ skills` stats, two-layer feature card, "Meet your new team" section now shows both Business Layer (16 cards) and Engineering Layer (19 cards) with full slash commands and attribution link.
- **`site/public/docs/`** — full mirror sync via `make docs-build`.
- **`docs/llms-full.txt`** — regenerated with 62 docs (added `engineering-layer.md`).
- **`.claude/rules/agents.md`** — both layers documented (16 + 19) with cross-layer handoff guidance.
- **`.claude/rules/skills.md`** — `dev-` category added with all 25 skills listed; total bumped to ~137.
- **`ROADMAP.md`** — new `v0.12 — Engineering Layer` section marking the deliverable as `[x]` with full agent / skill / template enumeration and recommended pipelines.

### Documentation

- **Engineering Layer attribution** — `NOTICE.md` at repo root + `README.md` Credits & Acknowledgments section + per-agent attribution comments + dedicated `docs/agents/engineering-layer.md`.
- **Pattern compliance** — all 19 engineering agents follow the EvoNexus standard pattern (rich frontmatter with Examples, Workspace Context, Shared Knowledge Base, Working Folder, Identity, Anti-patterns, Domain, How You Work, Skills You Can Use, Handoffs, Output Format, Continuity). Verified by `@lens-reviewer`, 3 fixes applied (oath-verifier `disallowedTools`, raven-critic and trail-tracer `Skills You Can Use` section).

## [0.11.4] - 2026-04-10

### Changed
- **Backup excludes reconstructible directories** — `backup.py` now excludes top-level dirs that don't contain user data: `site/`, `backups/`, `.venv/`, `_evo/`, `_evo-output/`. Also expanded `EXCLUDE_DIRS` to cover more cache/build folders (`.next`, `.cache`, `.local`, `build`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`). Reduces typical backup from ~63k files / 1GB to ~800 files / ~900MB while keeping all user data (workspace, agent-memory, custom skills, dashboard DB).
- **Custom skill convention unified** — product-specific skills (`int-licensing`, `int-whatsapp`, `prod-licensing-daily/weekly/monthly`, and the 45 `evo-*` skills) renamed to `custom-*` prefix so they're automatically gitignored via the existing `.claude/skills/custom-*` pattern. The `name:` frontmatter field in each `SKILL.md` was updated to match the new folder name (50 skills total).
- **Agent skill references updated** — `atlas-project`, `dex-data`, `nova-product`, `pulse-community` now reference the `custom-*` skill names instead of the old prefixed names.
- **`.gitignore` simplified** — removed the 5 explicit per-skill entries; the `.claude/skills/custom-*` pattern covers all custom skills.

## [0.11.3] - 2026-04-09

### Fixed
- **Stale folder references in docs** — replaced legacy Obsidian-style paths (`01 Daily Logs/`, `02 Projects/`, `05 Financeiro/`, `09 Estrategia/`) with new `workspace/` structure (`workspace/daily-logs/`, `workspace/projects/`, `workspace/finance/`, `workspace/strategy/`) in `CLAUDE.md`, status command, creating-skills/routines/updating guides, ops-vendor-review skill, and `llms-full.txt`.

### Changed
- **`.gitignore`** — added `config/triggers.yaml` to gitignored configs.

## [0.11.2] - 2026-04-09

### Added
- **SECURITY.md** — vulnerability disclosure policy with private reporting channels and contributor security guidelines

### Fixed
- **Command injection in dashboard backend** — replaced all `subprocess.run(..., shell=True)` with argument-list invocations across `systems.py`, `services.py`, and `tasks.py`; added container name validation and path traversal protection
- **WebSocket authentication bypass** — terminal WebSocket handler now verifies `current_user.is_authenticated` (previously skipped `before_request` middleware)
- **Code injection in MemPalace mining** — replaced f-string quote interpolation with `repr()` to prevent Python code injection via crafted path/wing values
- **Path traversal in MemPalace sources** — source paths now validated against home directory and workspace boundaries

## [0.11.1] - 2026-04-09

### Changed
- **Rebrand OpenClaude → EvoNexus** — full platform rename across ~80 files: docs, dashboard, CLI, site, templates, skills, agents, Docker, env vars (`OPENCLAUDE_PORT` → `EVONEXUS_PORT`), npm package (`@evoapi/evo-nexus`), GitHub repo (`EvolutionAPI/evo-nexus`), cover SVG, and all internal references.

## [0.11.0] - 2026-04-09

### Added
- **Workspace backup & restore** — new `backup.py` script that exports all gitignored user data (memory, agent-memory, config, dashboard DB, logs, custom agents/commands/templates/routines, `.env`) as a ZIP with manifest. Supports local storage (`backups/`) and S3-compatible cloud buckets. Restore with merge (skip existing) or replace (overwrite) mode.
- **Daily Backup routine** — core routine (`ADWs/routines/backup.py`) runs at 21:00 daily via scheduler. Pure Python (systematic, no AI, no tokens). Auto-uploads to S3 if `BACKUP_S3_BUCKET` is configured.
- **Backup dashboard page** — `/backups` page to list, create, download, restore, and delete backups from the browser. Shows S3 config status, backup metadata from manifest, and restore mode selection modal.
- **Trigger registry** — reactive event triggers (webhook & event-based) that execute skills or routines in response to external events. Supports GitHub, Stripe, Linear, Telegram, Discord, and custom webhooks with HMAC signature validation.
- **Triggers dashboard page** — `/triggers` page to create, edit, delete, test, enable/disable triggers. Copy webhook URL, regenerate secrets, view execution history.
- **`trigger-registry` skill** — CLI skill to create, manage, and test triggers.
- **Resume Claude sessions in chat** — dashboard chat now lists active/resumable Claude sessions with `--resume` support.
- **Makefile targets** — `make backup`, `make backup-s3`, `make restore`, `make backup-list`, `make backup-daily`.
- **S3 backup env vars** — `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `AWS_ENDPOINT_URL` in `.env.example`.

### Changed
- **Core routines** — 5 → 6 (Daily Backup added)
- **Dashboard screenshots** — all page screenshots optimized (50-70% smaller file sizes)
- **ROUTINES.md** — added Triggers and Daily Backup documentation sections
- **docs/** — updated core-routines, makefile reference, env-variables reference, dashboard overview

## [0.10.1] - 2026-04-09

### Fixed
- **Site and docs counts** — updated all references from 9/10 agents to 16, from ~68/~80 skills to ~130, across site Home page, introduction, architecture, getting-started, using-agents, initial-setup, dashboard overview, and evolution-foundation case study
- **Site Home features** — added Channels, Agent Teams, and Scheduled Tasks to the features grid; updated agent showcase to show all 16 agents
- **Channels docs in pt-BR** — rewrote `docs/guides/channels.md` and `docs/guides/channels-reference.md` to English (docs should always be in English)
- **README screenshots** — restored screenshots section using HTML `<img>` tags with consistent sizing (were broken by markdown table layout)

## [0.10.0] - 2026-04-09

### Added
- **6 new core agents** — Mako (Marketing), Aria (HR/People), Zara (Customer Success), Lex (Legal/Compliance), Nova (Product), Dex (Data/BI). Each with system prompt, slash command, dashboard card with icon and color, and dedicated skills.
- **~80 new skills** — HR (`hr-*`), Legal (`legal-*`), Ops (`ops-*`), Product Management (`pm-*`), Customer Success (`cs-*`), Data/BI (`data-*`), Marketing (`mkt-*`). Skill count: ~68 → ~180.
- **Channels** — bidirectional chat bridges that push messages into a running Claude Code session. Discord and iMessage channels added alongside existing Telegram. Each runs as a background screen session.
- **Channel documentation** — `docs/guides/channels.md` (setup guide for all 3 channels) and `docs/guides/channels-reference.md` (technical reference for building custom channels/webhooks).
- **Dashboard channels section** — Services page now shows "Channels" as a separate section with Telegram, Discord Channel, and iMessage Channel cards (Start/Stop/Logs).
- **Agent documentation** — individual doc pages for all 16 agents in `docs/agents/`.
- **Makefile targets** — `discord-channel`, `discord-channel-stop`, `discord-channel-attach`, `imessage`, `imessage-stop`, `imessage-attach`.

### Changed
- **Agent count** — 10 → 16 core agents across README, docs, dashboard, and rules
- **Skill count** — ~68 → ~180 across README, docs, and dashboard
- **Dashboard AGENT_META** — all 16 agents now have dedicated icons, colors, and command badges
- **README** — updated architecture diagram, agent list, skill count, dashboard features, and workspace structure

## [0.9.0] - 2026-04-09

### Added
- **Custom agents** — user-created agents with `custom-` prefix. Gitignored, auto-discovered by dashboard (gray "custom" badge vs green "core" badge). Backend returns `custom`, `color`, `model` fields from frontmatter.
- **Oracle agent** — 10th core agent. `/oracle` workspace knowledge agent that answers questions about agents, skills, routines, integrations, and configuration by reading the actual documentation. No RAG needed — reads `docs/llms-full.txt` and source files directly.
- **`create-agent` skill** — conversational interface to create custom agents (name, domain, personality, model, color, memory folder, slash command)
- **`create-command` skill** — conversational interface to create standalone slash commands for Claude Code

### Changed
- **Agent count** — 9 → 10 core agents (Oracle added) across README, docs, and rules
- **Dashboard Agents page** — core/custom badges, dynamic colors from frontmatter for custom agents, separate core/custom counters in stats bar
- **Documentation** — updated agents overview, creating-agents guide (core vs custom section), skills overview

## [0.8.0] - 2026-04-09

### Added
- **Scheduled Tasks** — new one-off task scheduling system. Schedule a skill, prompt, or script to run at a specific date/time without creating a full routine. Dashboard page at `/tasks` with create/edit/cancel/run-now/view-result. API CRUD at `/api/tasks`. Scheduler checks pending tasks every 30 seconds.
- **`schedule-task` skill** — conversational interface to create scheduled tasks ("agendar pra sexta 10h", "schedule this for tomorrow")
- **Dynamic routine discovery** — `ROUTINE_SCRIPTS` and `SCRIPT_AGENTS` are no longer hardcoded. Agent and script mappings are built dynamically by scanning `ADWs/routines/` scripts and extracting metadata from docstrings (`via AgentName` pattern). New scripts are auto-discovered.
- **`make run R=<id>`** — generic dynamic runner for any routine (core or custom)
- **`make list-routines`** — lists all discovered routines with agent, script, and name
- **Workspace file browser** — reports page replaced with a full file browser that navigates workspace folders

### Changed
- **Makefile cleaned** — custom routine targets (user-specific) removed from Makefile. Only core routine targets remain (`morning`, `eod`, `memory`, `memory-lint`, `weekly`). Custom routines run via `make run R=<id>`.
- **`ROUTINES.md`** — expanded with scheduled tasks docs, dynamic discovery, and updated manual execution section
- **Documentation** — new `docs/routines/scheduled-tasks.md`, updated makefile reference, dashboard overview, creating-routines guide, and skills overview

## [0.7.0] - 2026-04-09

### Added
- **Systematic routines** — new `run_script()` function in `ADWs/runner.py` for pure Python routines that run without Claude CLI, without AI, without tokens. Same logging/metrics infrastructure, but cost=$0 and duration in seconds instead of minutes.
- **`create-routine` skill updated** — now asks "AI or systematic?" and generates the correct script pattern. For systematic routines, Claude writes the Python logic once at creation time, then the script runs on its own forever.
- **Example routine** — `ADWs/routines/examples/log_cleanup.py` demonstrates the systematic pattern (deletes logs older than 30 days)
- **"systematic" badge** — dashboard Scheduler and Routines pages show a gray "systematic" badge for system routines instead of green `@agent`
- **Site docs CSS overhaul** — replaced fragile custom marked renderers with CSS-based styling on `.docs-content`. Tables, lists, code blocks, and all markdown elements now render correctly with the dark theme.
- **OAuth redirect URLs** — documented redirect URIs for YouTube, Instagram, and LinkedIn OAuth setup

### Changed
- **ROADMAP** — "Agent-less routines" marked as done

## [0.6.1] - 2026-04-09

### Added
- **Core routines documentation** (`docs/routines/core-routines.md`) — detailed explanation of all 5 core routines: what they do, why they matter, and how they form the daily loop
- **Memory Lint promoted to core** — moved from `ADWs/routines/custom/` to `ADWs/routines/`, hardcoded in `scheduler.py` (Sunday 09:00). Now 5 core routines instead of 4
- **Release skill** now syncs screenshots (`public/print-*.png` → `site/public/assets/`) on every release

### Changed
- **Dashboard pages redesigned** — 12 pages (Audit, Config, Costs, Files, Integrations, Memory, Reports, Roles, Routines, Scheduler, Skills, Systems, Templates, Users) with consistent dark theme and improved UX
- **Integration count** — 19 → 17 (removed internal-only Licensing and WhatsApp docs from public documentation)
- **Memory system** — LLM Wiki pattern: ingest propagation, weekly lint, centralized index, and operation log

### Removed
- **`docs/integrations/licensing.md`** — internal only, not public
- **`docs/integrations/whatsapp.md`** — internal only, not public

### Fixed
- **Dashboard build** — removed unused `totalTokens` variable in Costs page that blocked TypeScript compilation

## [0.6.0] - 2026-04-09

### Added
- **Evolution API skill** (`int-evolution-api`) — 33 commands: instances, messages (text, media, location, contact, buttons, lists, polls), chats, groups, webhooks
- **Evolution Go skill** (`int-evolution-go`) — 24 commands: instances, messages, reactions, presence
- **Evo CRM skill** (`int-evo-crm`) — 48 commands: contacts, conversations, messages, inboxes, pipelines, labels
- **Integration docs** — 3 new guides: `docs/integrations/evolution-api.md`, `evolution-go.md`, `evo-crm.md`
- **Dashboard integrations** — Evolution API, Evolution Go, and Evo CRM cards on Integrations page
- **`.env.example`** — added `EVOLUTION_API_URL/KEY`, `EVOLUTION_GO_URL/KEY`, `EVO_CRM_URL/TOKEN`

### Changed
- **Integration count** — 16 → 17 across README, site, and docs (removed internal-only Licensing and WhatsApp docs)
- **Community members** — 7,000+ → 17,000+ on site
- **v0.4 roadmap complete** — all 13 items done, Evolution product skills was the last one

## [0.5.1] - 2026-04-09

### Changed
- **Docs markdown rendering** — replaced regex parser with `marked` library. Code blocks, ASCII art, and nested formatting now render correctly on the site.
- **README and site** — `npx @evoapi/evo-nexus` is now the primary install method. Git clone shown as alternative.
- **Release skill** — `make docs-build` and frontend rebuild are now mandatory on every release (not conditional).

### Fixed
- **Site /docs navigation** — nested doc pages (e.g., `/docs/guides/creating-routines`) no longer 404. Switched from `useRoute` wildcard to direct URL parsing.
- **Site route matching** — changed from `/docs/:slug+` to `/docs/*` for reliable wouter matching.
- **CLI default directory** — `npx @evoapi/evo-nexus` without args now clones into current directory (`.`), not a subfolder.
- **Site CI build** — added missing `print-agents.png` to site assets.
- **Docs sync** — site now serves updated docs matching the repo (was stale).

## [0.5.0] - 2026-04-09

### Added
- **Active agent visualization** — Claude Code hooks (`PreToolUse`, `Stop`) track agent launches in `agent-status.json`. Dashboard polls `/api/agents/active` and shows animated "RUNNING" badges on agent cards and overview.
- **Agents page redesign** — unique icons and accent colors per agent, slash command badges, memory count pills, status dots, hover glow effects.
- **Overview page redesign** — stat cards with icons and trend indicators, active agents bar, quick actions row (Morning Briefing, Chat, Costs, GitHub), improved reports and routines tables with relative timestamps.
- **Claude Code hooks** — `agent-tracker.sh` hook registered in `settings.json` for real-time agent activity tracking.
- **Project settings.json** — permissions (allow/deny rules), hooks configuration.
- **Inner-loop commands** — `/status` (workspace status) and `/review` (recent changes + next actions).
- **Default system: Claude Status** — `seed_systems()` creates Anthropic status page as default external system on first boot.
- **Public roadmap** — `ROADMAP.md` with community input via GitHub discussions.

### Changed
- **CLAUDE.md split** — reduced from 263 to 128 lines. Detailed config moved to `.claude/rules/` (agents, integrations, routines, skills) — auto-loaded by Claude Code.
- **All 9 agent prompts generalized** — removed hardcoded personal references (Omie, Linear, Discord Evolution, Brazilian formats, etc.). User-specific context preserved in `_improvements.md` per agent memory folder.
- **Rules and commands translated** — all `.claude/rules/` and `.claude/commands/` files translated from Portuguese to English.

## [0.4.1] - 2026-04-09

### Added
- **Docker Compose for dashboard** — `Dockerfile.dashboard` (multi-stage: node + python) + `docker-compose.yml` with dashboard, telegram, and runner services. `make docker-dashboard` to start.
- **Dashboard CI** — GitHub Actions workflow builds and pushes dashboard image to `ghcr.io/evolutionapi/evo-nexus/dashboard` on push/release
- **npm CI** — GitHub Actions workflow publishes CLI to npm on release (requires `NPM_TOKEN` secret)

### Changed
- **Sidebar reorganized** — 5 collapsible groups (Main, Operations, Data, System, Admin) with collapse state persisted in localStorage
- **Scheduler removed from docker-compose** — runs embedded in dashboard, not as separate service
- **`make docker-up` → `make docker-telegram`** — reflects that only Telegram is a separate Docker service
- **Public roadmap updated** — removed internal Future/Research section, marked completed items

## [0.4.0] - 2026-04-09

### Added
- **CLI installer** — `npx @evoapi/evo-nexus` clones repo, checks prerequisites, installs deps, runs setup wizard, and builds dashboard
- **Version indicator in dashboard** — sidebar footer shows current version; `/api/version/check` compares against latest GitHub release with 1h cache
- **Public roadmap** — `ROADMAP.md` with 4 phases (v0.4 → Future), community input via GitHub discussions
- **Update guide** — `docs/guides/updating.md` with git pull, Docker, and custom content preservation instructions

### Changed
- **Privacy-first licensing** — removed heartbeat thread, deactivate endpoint, and shutdown hook. Only initial registration remains (who installed). No monitoring, no kill switch, no telemetry.
- **Licensing version** — now reads from `pyproject.toml` dynamically instead of hardcoded constant

### Fixed
- **nginx 403 on `/docs/`** — removed `$uri/` from `try_files` so directory paths fall through to SPA instead of returning Forbidden
- **`.gitignore` formatting** — `site/lib/` and `mempalace.yaml` were concatenated on one line
- **User-specific files removed from git** — `mempalace.yaml` and `entities.json` no longer tracked

## [0.3.2] - 2026-04-08

### Added
- **Docs page on site** (`/docs`) — full documentation viewer with sidebar, search, and markdown rendering
- **Auto-version system** — `pyproject.toml` is single source of truth, injected into site (Vite `__APP_VERSION__`), dashboard (`/api/version`), and CI (Docker build-arg)
- **Pre-build docs index** — `scripts/build-docs-index.mjs` generates `docs-index.json` at build time
- **`/api/version` endpoint** — dashboard serves current version from `pyproject.toml`

### Changed
- **`make docs-build`** — now also syncs `docs/` to `site/public/docs/`
- **Docs links** in landing page point to `/docs` (internal route, not dashboard)
- **Site version badge** — reads from `pyproject.toml` dynamically instead of hardcoded

## [0.3.1] - 2026-04-08

### Added
- **Landing page** (`site/`) — standalone React + Vite static site, extracted from Replit monorepo
- **Docker support for site** — multi-stage Dockerfile (node build → nginx serve) + docker-compose
- **GitHub Actions CI** — workflow builds site image and pushes to `ghcr.io/evolutionapi/evo-nexus/site` on push/release
- **Docs bundled in site image** — `docs/` copied into site build context automatically

### Changed
- **`.gitignore` updated** — site tracked in repo (Replit artifacts, node_modules, dist excluded)
- **Site assets renamed** — clean filenames (`logo.png`, `print-overview.png`, etc.) instead of Replit hashes

## [0.3.0] - 2026-04-08

### Added
- **Public Documentation** (`/docs`) — full docs site inside the dashboard, accessible without auth
- **MemPalace** — semantic knowledge base with ChromaDB for code/doc search (optional)
- **Content search** — docs search now matches inside file content, not just titles
- **llms-full.txt** — pre-generated plain text with all docs for LLM consumption (`/docs/llms-full.txt`)
- **23 routine examples** and **21 template examples** shipped with repo
- **14 documentation screenshots** in `docs/imgs/`
- **Comprehensive docs** — 28 markdown files across 9 sections (guides, dashboard, agents, skills, routines, integrations, real-world, reference)
- **Practical usage guides** — how to run routines, invoke agents, create custom skills

### Changed
- **Unofficial disclaimer** — README, docs, and landing page clearly state "unofficial, not affiliated with Anthropic"
- **Positioning** — "compatible with Claude Code and other LLM tooling" (not "purpose-built for")
- **Enterprise-safe language** — "integrates with" instead of "leverages", opens door for multi-provider future
- **Docs sidebar** — logical section ordering, section icons, content preview in search
- **llms-full.txt** — served as static pre-generated file (instant load, no on-the-fly concatenation)
- **i18n** — final cleanup, 18 files translated from Portuguese to English

### Fixed
- `/docs/llms-full.txt` redirect (was showing docs sidebar with "Loading..." instead of plain text)
- Screenshots with personal data removed and replaced
- 10 doc files corrected after full audit

## [0.2.0] - 2026-04-09

### Added
- **Core vs Custom split** — routines, templates, and skills separated into core (tracked) and custom (gitignored)
- **Create Routine skill** (`create-routine`) — guides users through creating custom routines step by step
- **Scheduler embedded in dashboard** — runs automatically with `make dashboard-app`, no separate process
- **Core/Custom badges** — scheduled routines and templates show green "core" or gray "custom" labels
- **Custom routines from YAML** — scheduler loads custom routines dynamically from `config/routines.yaml`
- **.env editor** — edit environment variables directly from the Config page in the dashboard
- **Auto-discover reports** — Reports page scans entire `workspace/` recursively, no hardcoded paths

### Changed
- **Routines reorganized** — 4 core routines in `ADWs/routines/`, custom in `ADWs/routines/custom/` (gitignored)
- **Templates reorganized** — 2 core HTML + 4 core MD templates, custom in `custom/` subfolders (gitignored)
- **`ADWs/rotinas/` renamed to `ADWs/routines/`** — full English naming
- **Agent files renamed** — `flux-financeiro` → `flux-finance`, `nex-comercial` → `nex-sales`
- **59 evo-* skills removed** — Evo Method is a separate project, skills gitignored
- **Docker removed from Services** — use Systems CRUD for Docker container management
- **ROUTINES.md rewritten** — generic, documents core vs custom split and YAML config format
- **scheduler.py rewritten** — only 4 core routines hardcoded, custom loaded from YAML
- **README updated** — correct agent names (`/clawdia`, `/flux`, `/atlas`, etc.), 4 core routines, ~67 skills

### Removed
- **ROADMAP.md** from Config page (file no longer exists)
- **Docker section** from Services page
- **Specific routine schedules** from scheduler.py (moved to user's `config/routines.yaml`)
- **Custom routines from git** — 23 scripts moved to gitignored `custom/` directory
- **Custom templates from git** — 15 HTML + 6 MD templates moved to gitignored `custom/` directories

### Fixed
- Custom routine scripts `sys.path` adjusted for `custom/` subdirectory (3 levels up for runner)
- Scheduler parser strips `custom/` prefix for agent mapping
- `SCRIPT_AGENTS` moved to module level (was inaccessible from `_load_yaml_routines`)
- Telegram `screen` command removed unsupported `-Logfile` flag
- Remaining Portuguese translated in skill bodies

## [0.1.1] - 2026-04-08

### Added
- **Silent Licensing** — automatic registration via Evolution Foundation licensing server
- **Systems CRUD** — register and manage apps/services from the dashboard
- **Roles & Permissions** — custom roles with granular permission matrix
- **Onboarding Skill** (`initial-setup`) — guides new users through the workspace
- **Screenshots** in README (overview, chat, integrations, costs)

### Changed
- **English-first codebase** — translated agents, skills, templates, routines, and config
- **Workspace folders** renamed from PT to EN (`workspace/daily-logs`, etc.)
- **Setup wizard** simplified — all agents enabled by default
- **HTML templates** standardized with Evolution Foundation branding
- **Makefile** auto-detects `uv` or falls back to `python3`
- All Python dependencies consolidated in `pyproject.toml`

### Removed
- **Evo Method** (`_evo/`) — separate project
- **Proprietary skills** — licensing and whatsapp excluded
- **Portuguese folder names** (01-09) — replaced with `workspace/`

### Fixed
- 16 bug fixes (scheduler logs, SQLite WAL, auth permissions, dates, etc.)

## [0.1.0] - 2026-04-08

### Added
- Initial open source release
- 9 Specialized Agents, ~67 Skills, 4 core routines
- Web Dashboard with auth, roles, web terminal, service management
- Integration clients (Stripe, Omie, YouTube, Instagram, LinkedIn, Discord)
- ADW Runner with token/cost tracking
- Persistent memory system
- Setup wizard (CLI + web)
