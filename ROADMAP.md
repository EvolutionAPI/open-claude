# EvoNexus Roadmap

> Execution roadmap derived from the PRD review and current branch state.
> Last updated: 2026-04-24

---

## How To Read This

- `Done` means implemented and validated locally.
- `Partial` means a scaffold or mitigation exists, but the item is not closed.
- `Next` means highest priority pending work.
- `Later` means important work that is gated by dependencies.

---

## Project Snapshot

- Delivered: the security hardening pass, backend maintainability work, frontend scaling work, and the phase 4 platform layer are in place.
- Open: env normalization edge cases in the last offline tooling paths.
- Focus now: close the remaining partial items before adding new feature surface area.

---

## Current Baseline

| Area | Status | Notes |
|---|---|---|
| Security | Done | Login hardening, password policy, configurable CORS, env-first secret key handling, CSRF token plumbing, session token rotation, and 2FA/TOTP are in place. |
| Reliability | Done | Session GC, heartbeat timeout handling, health endpoints, backup hooks, restart supervision, and readiness/liveness probe split are in place. |
| Architecture | Partial | Alembic bootstrap, lazy blueprint loading, structured logs, terminal-server modularization, and restart supervision are in place. Remaining work: the last env normalization edge cases. |
| Frontend | Done | Route splitting, section-level error boundaries, theme toggle, PWA support, command palette, and mobile chat improvements are done. |
| Testing / CI | Done | Auth tests, terminal-server tests, CI, pre-commit hooks, and Playwright E2E coverage exist. |
| Platform | Done | Queue/cache abstractions, provider failover, observability, plugins, a shared platform broker, and PostgreSQL rollout wiring are in place. |

---

## Shipped So Far

- Rate limiting on login
- Strong password policy
- Configurable CORS
- Env-first secret key handling
- Runtime config aliases for `DATABASE_URL` and `PORT`
- CSRF token plumbing for mutating requests
- Per-session token rotation and CSRF refresh on auth changes
- TOTP / 2FA enrollment, login, and disable flows for admins
- Readiness / liveness health endpoints
- Pre-commit hooks for backend lint, frontend format, and frontend type-check
- Pre-migration backup hook for SQLite
- Alembic-backed schema bootstrap
- Session GC in the terminal server
- Heartbeat, summary, and goal workers now follow the shared DB resolver
- WebSocket heartbeat timeout handling
- Terminal-server audit log
- Structured JSON logs for backend and terminal server
- Health and deep-health endpoints
- Healthcheck wiring in compose / swarm
- Session save debounce in the terminal server
- Lazy blueprint loading
- Terminal-server restart supervision
- Terminal-server runtime split into a wrapper plus dedicated runtime module
- Shared platform event broker between Flask and terminal-server
- Hot-path cache invalidation on platform events
- Frontend route splitting
- Section-level error boundaries
- Global theme toggle
- Command palette with Ctrl+K
- PWA manifest and service worker
- Mobile chat layout improvements
- AgentChat transcript shell extraction
- AgentChat block extraction into focused components
- Integrations page decomposition into focused modules
- Shared `PageSkeleton` loading states across major pages
- Provider failover routing and preflight selection
- Observability dashboard
- Plugin registry and install / uninstall flow
- PostgreSQL-ready runtime and DB adapters
- Compose and Swarm PostgreSQL rollout wiring
- CI workflow for backend, terminal server, and frontend build
- Playwright E2E coverage for setup, login, and protected-route navigation

---

## Delivery Roadmap

### Phase 1 - Close Remaining Risk

Goal: make the current stack safe enough for sensitive data and stable deployments.

| Item | Priority | Status | Exit Criterion |
|---|---|---|---|
| D6 Backup before migrations | P0 | Done | Automatic backup runs before any schema change. |
| S4 CSRF tokens for mutations | P1 | Done | Mutating requests now require the XHR header plus a per-session CSRF token. |
| S5 Audit log for terminal server | P1 | Done | Sensitive actions are recorded with actor, timestamp, and target. |
| P5 WebSocket heartbeat timeout | P1 | Done | Dead connections are detected and closed automatically. |
| T2 Terminal-server integration tests | P1 | Done | WebSocket session lifecycle is covered by automated tests. |
| D1 / D2 Health checks and probes | P1 | Done | Separate readiness and liveness endpoints are exposed and the deploy healthchecks use the live probe. |

Exit criterion: no remaining P0 security gaps, and unhealthy processes are detected automatically.

### Phase 2 - Backend Maintainability

Goal: reduce startup coupling and make migrations and runtime behavior explicit.

| Item | Priority | Status | Exit Criterion |
|---|---|---|---|
| A1 Alembic extraction | P1 | Done | Schema changes are versioned and reversible. |
| A2 Split `server.js` | P2 | Done | `server.js` now delegates to a dedicated runtime module and platform event broker. |
| D3 Structured logs | P2 | Done | Logs are JSON and searchable across services. |
| D4 Env-based config | P1 | Partial | Most runtime config is env-driven; `DATABASE_URL` and `PORT` aliases are supported, and the heartbeat, summary, and goal workers now follow the shared DB resolver, but a few offline tools still keep local-path fallbacks. |
| D5 Isolated process restart | P1 | Done | Terminal-server failure no longer brings down the dashboard. |
| P3 Debounce `saveSessionsToDisk` | P2 | Done | Disk writes are batched and bounded. |
| P4 Lazy blueprint loading | P2 | Done | Backend startup avoids eager loading every route. |

Exit criterion: backend startup is faster, migrations are explicit, and service boundaries are clearer.

### Phase 3 - Frontend Scale And UX

Goal: keep the dashboard maintainable as pages and workflows grow.

| Item | Priority | Status | Exit Criterion |
|---|---|---|---|
| U1 Decompose `AgentChat.tsx` | P2 | Done | Core chat blocks and the transcript shell are split into focused components. |
| U2 Decompose `Integrations.tsx` | P2 | Done | Provider-specific logic, social accounts, and database flows are split into focused modules. |
| U3 Theme toggle | P3 | Done | Light and dark preference is user-controlled. |
| U4 PWA support | P3 | Done | Dashboard has a manifest and service worker. |
| U5 Skeleton states everywhere | P2 | Done | Every major page now uses the shared `PageSkeleton` loading surface. |
| U7 Command palette | P3 | Done | Keyboard-driven navigation is available. |
| 4.4 Mobile responsive chat | P2 | Done | Chat works on narrow screens without layout breakage. |

Exit criterion: the dashboard can absorb new pages without becoming a monolith.

### Phase 4 - Platform Expansion

Goal: unlock multi-provider, observability, and enterprise deployment paths.

| Item | Priority | Status | Exit Criterion |
|---|---|---|---|
| A3 Message queue | P2 | Done | Queue events now flow through a shared broker between Flask and terminal server. |
| A4 Redis cache | P3 | Done | Provider, observability, and queue hot paths now use cache-backed reads with event-driven invalidation. |
| A5 PostgreSQL option | P2 | Done | Compose and Swarm now wire `DATABASE_URL` to a PostgreSQL service. |
| 4.1 Native provider failover | P2 | Done | Routing is configurable and the terminal server now preflights and falls back through ready providers. |
| 4.2 Observability dashboard | P2 | Done | Tokens, latency, queue, cache, and plugin state are visible in one place. |
| 4.3 Plugin system | P2 | Done | Third-party agent packs can be registered, installed, and removed safely. |
| 4.5 PostgreSQL backend | P2 | Done | DB adapter and migrations work across SQLite and PostgreSQL. |

Exit criterion: the platform can scale across load, providers, and deployment models.

---

## Priority Backlog

### Security

- No open Phase 1 security items remain.

### Reliability

- No open Phase 1 reliability items remain.

### Architecture

- D4 Config normalization

### Testing / CI


No open Testing / CI items remain.

### Frontend / UX

- No open Phase 3 frontend items remain.

### Platform Expansion

- No open Platform Expansion items remain.

---

## Sprint Execution Plan

Priority inside each sprint runs top to bottom. The `Depends On` column lists hard blockers only; the sprint order itself also reflects risk reduction and release sequencing.

Implementation status: Sprint 1 is complete, Sprint 2 is partially complete, Sprint 3 is complete, and Sprint 4 is complete.

### Sprint 1 - Security And Deploy Gates

Goal: close the items that reduce blast radius and make production checks reliable.

| Item | Priority | Depends On | Why It Is Here |
|---|---|---|---|
| S4 CSRF tokens for mutations | P1 | None | Must land before any new write-heavy surface area expands. |
| D1 / D2 health checks and probes | P1 | None | Separate readiness and liveness before more rollout work. |
| S6 session key rotation | P2 | None | Completes the auth hardening pass while the auth path is already being touched. |

### Sprint 2 - Config And Auth Hardening

Goal: normalize runtime configuration and finish the remaining auth hardening.

| Item | Priority | Depends On | Why It Is Here |
|---|---|---|---|
| D4 config normalization | P1 | None | Remove the last hardcoded runtime assumptions before deeper refactors. |
| S7 2FA / TOTP for admins | P2 | S4 + S6 | Builds on the hardened login and session flow. |
| A2 `server.js` modularization | P2 | D4 | Refactor after the config surface is stable. |
| T5 pre-commit hooks | P2 | Done | Lint, format, and frontend type-check gates run before commits. |

### Sprint 3 - Verification And Scale Prep

Goal: prove the stable flows end to end and prepare the platform layer for scale.

| Item | Priority | Depends On | Why It Is Here |
|---|---|---|---|
| T3 Playwright E2E | P2 | Done | Validates the core user journeys after the config and auth work settle. |
| A3 Message queue | P2 | Done | Async coordination is now handled by the shared platform broker. |
| A4 Redis cache | P3 | Done | Hot-path caching is now active with invalidation on platform events. |

### Sprint 4 - Production Rollout

Goal: finish the remaining deployment wiring for PostgreSQL-backed production use.

| Item | Priority | Depends On | Why It Is Here |
|---|---|---|---|
| A5 PostgreSQL option | P2 | Done | PostgreSQL rollout wiring is now present in both Compose and the Swarm stack. |

---

## Dependency Rules

- S4 should land before any new write-heavy surfaces.
- P5 should land before more WebSocket features are built.
- 4.1 should reuse the current Smart Router instead of duplicating provider loading logic.
- D4 remains the only partially open configuration cleanup item.

---

## Success Metrics

| Metric | Target |
|---|---|
| First Contentful Paint | < 1.5s |
| Bundle size gzipped | < 400KB |
| Auth coverage | >= 80% |
| Terminal server WebSocket coverage | >= 70% |
| Login brute-force attempts | Bounded by lockout policy |
| Session GC lag | <= 24h idle |
| Backend startup time | < 2s |

---

## Notes

- This file replaces the old v0.4-v1.0 milestone list.
- The next concrete delivery gate is D4 cleanup, which should be treated as the current execution queue.
