# Architecture

## Overview

EvoNexus is a file-based, git-friendly framework. Everything is markdown, YAML, and Python scripts. No database required for the core framework (SQLite is used only by the dashboard).

EvoNexus organizes 38 agents in **two ortogonal layers**: a Business Layer (17 agents for ops/finance/community/learning retention/etc.) and an Engineering Layer (21 agents for software dev — 19 derived from [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode), MIT, by Yeachan Heo, plus 2 native: Helm and Mirror). The two layers share the same skill, memory, and integration infrastructure but stay out of each other's way: business tasks route to business agents, engineering tasks to engineering agents. Cross-layer handoffs are common (e.g., Nova writes a PRD → Apex reviews → Bolt implements → Mirror captures lessons). The engineering layer follows a canonical 6-phase workflow (Discovery → Planning → Solutioning → Build → Verify → Retro) documented in [`.claude/rules/dev-phases.md`](https://github.com/EvolutionAPI/evo-nexus/blob/main/.claude/rules/dev-phases.md).

```
┌──────────────────────────────────────────────────────────────────────┐
│                            User (human)                              │
│                                  │                                   │
│                            Claude Code CLI                           │
│                                  │                                   │
│   ┌────────────────────────────────────────────────────────────┐    │
│   │  BUSINESS LAYER (17) — operations / finance / community    │    │
│   │  Clawdia Flux Atlas Pulse Pixel Sage Nex Mentor Lumen      │    │
│   │  Kai Oracle Mako Aria Zara Lex Nova Dex                    │    │
│   └──────────────────────────┬─────────────────────────────────┘    │
│                              │                                       │
│   ┌──────────────────────────┴─────────────────────────────────┐    │
│   │  ENGINEERING LAYER (19) — software development             │    │
│   │  apex echo compass raven bolt hawk lens zen vault grid     │    │
│   │  probe oath trail scout flow scroll quill canvas prism     │    │
│   │  (derived from oh-my-claudecode by Yeachan Heo, MIT)       │    │
│   └──────────────────────────┬─────────────────────────────────┘    │
│                              │                                       │
│   ┌──────────────────────────┴─────────────────────────────────┐    │
│   │  Skills (150+)                                              │    │
│   │  Business: fin- / social- / int- / hr- / legal- / pm- /... │    │
│   │  Engineering: dev-* (25 skills, 3 tiers)                   │    │
│   └──────────────────────────┬─────────────────────────────────┘    │
│                              │                                       │
│   ┌──────────────────────────┴─────────────────────────────────┐    │
│   │  Integrations (APIs + MCPs)                                │    │
│   │  Gmail / Calendar / Discord / Stripe / GitHub / Linear /…  │    │
│   └────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘

        ┌───────────────────────┐
        │   Scheduler (cron)    │ ─── routines.yaml
        │   ADW Runner          │ ─── 4 core + ~23 custom examples
        │   JSONL Logs          │ ─── metrics + costs
        └───────────────────────┘

        ┌───────────────────────┐
        │   Dashboard (web)     │
        │   Flask + React       │
        │   SQLite (auth only)  │
        └───────────────────────┘
```

## Components

### Agents (`.claude/agents/`)

Each agent is a markdown file with a system prompt that defines its domain, responsibilities, and behavioral rules. Agents are invoked via slash commands (`/clawdia-assistant`, `/flux-finance`, `/apex-architect`, `/bolt-executor`, etc.) or automatically by Claude based on the user's request.

### Skills (`.claude/skills/`)

Skills are domain-specific instructions that teach Claude how to perform specific tasks. Organized by prefix:

| Prefix | Domain | Count |
|--------|--------|-------|
| `social-` | Social media | 17 |
| `int-` | Integrations | 13 |
| `fin-` | Financial | 11 |
| `prod-` | Productivity | 9 |
| `mkt-` | Marketing | 8 |
| `gog-` | Google | 6 |
| `obs-` | Obsidian | 5 |
| `discord-` | Discord | 5 |
| `pulse-` | Community | 4 |
| `sage-` | Strategy | 3 |

> **Note:** `evo-` skills (~45) are maintained in the separate [EVO-METHOD](https://github.com/EvolutionAPI/EVO-METHOD) project. They are gitignored from this repo but work normally if installed locally. The repo ships 150+ non-evo skills.

### Routines (`ADWs/routines/`)

Automated workflows that run on a schedule. Each routine is a Python script that invokes Claude Code CLI with a specific agent and skill.

Routines are split into two tiers:
- **Core** (`ADWs/routines/`) — 4 routines shipped with the repo (good_morning, end_of_day, memory_sync, weekly_review).
- **Examples** (`ADWs/routines/examples/`) — ~23 example routines tracked with the repo (community, finance, social, licensing, etc.).
- **Custom** (`ADWs/routines/custom/`) — user-created routines (gitignored). Copy from examples or create your own.

**Runner** (`ADWs/runner.py`) — The execution engine that:
- Invokes Claude Code CLI with `--output-format json`
- Captures token usage and cost
- Logs to JSONL files
- Sends Telegram notifications
- Tracks metrics per routine

**Scheduler** (`scheduler.py`) — Reads `config/routines.yaml` and runs routines at configured times using the `schedule` library.

### Memory

Two-tier persistent memory following the **LLM Wiki pattern** (ingest → query → lint):

1. **CLAUDE.md** — Hot cache loaded at every session start. Contains key context about the user, company, active projects, and preferences.
2. **memory/** — Global memory directory with typed files (people, projects, glossary, trends). Agents read these as needed.
   - `index.md` — Centralized catalog of all memory files by category (auto-updated by memory-sync)
   - `log.md` — Append-only chronological record of all memory operations (ingest, lint, updates)
3. **agent-memory/** — Per-agent memory that persists between sessions.

Three operations maintain the knowledge base:
- **Ingest** (daily, via memory-sync) — Extracts new knowledge from daily logs, meetings, and git changes. Propagates updates across related memory files (e.g., a person's role change updates their people/ file, glossary.md, and CLAUDE.md).
- **Query** (during conversations) — Complex syntheses can be filed back as new memory entries, so knowledge compounds through use.
- **Lint** (weekly, via memory-lint) — Health check that detects contradictions, stale claims, orphan files, coverage gaps, and missing cross-references.

### Dashboard (`dashboard/`)

Web UI built with:
- **Backend**: Flask + SQLAlchemy + Flask-Login + WebSocket
- **Frontend**: React + TypeScript + Tailwind + Recharts + xterm.js
- **Auth**: SQLite with roles (admin/operator/viewer), customizable permissions, audit log
- **Terminal**: Real browser-based Claude Code terminal via WebSocket PTY

### Integrations

API clients in `.claude/skills/int-*/scripts/` that connect to external services. Each integration has a SKILL.md describing usage and a Python client script.
