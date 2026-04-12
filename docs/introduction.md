# What is EvoNexus

> **Note:** EvoNexus is an independent, **unofficial open-source project**. It is **not affiliated with, endorsed by, or sponsored by Anthropic**. "Claude" and "Claude Code" are trademarks of Anthropic, PBC. This project integrates with Claude Code as a third-party tool and requires users to provide their own installation and credentials.

## The Problem

Running a business means juggling dozens of tools, dashboards, and communication channels every day. Email, calendar, project management, financial tracking, community moderation, social media — each one demands attention, and none of them talk to each other.

Most "AI assistants" are chatbots. You ask a question, you get an answer, and then you're back to manually copying data between tools. That doesn't scale.

## What EvoNexus Is

EvoNexus is a multi-agent workspace compatible with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and other LLM tooling. It turns a single Claude Code installation into a team of **38 specialized agents** organized in two ortogonal layers — one for business operations, one for software engineering.

The **Business Layer** has 17 agents that own distinct domains (finance, projects, community, social media, strategy, sales, courses, learning retention, personal wellness, marketing, HR, customer success, legal, product, data, knowledge) and produce real operational outputs: HTML reports, triaged inboxes, synced meeting notes, financial snapshots, community health checks.

The **Engineering Layer** has 21 agents for software development (architecture, planning, implementation, code review, testing, debugging, security, design, cycle orchestration, retrospective) — 19 derived from [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode) (MIT, by Yeachan Heo) + 2 native (`helm-conductor` for cycle orchestration and `mirror-retro` for blameless retrospectives). The layer follows a canonical 6-phase workflow (Discovery → Planning → Solutioning → Build → Verify → Retro) that takes a brief all the way to a verified, reviewed, tested feature with captured lessons.

A scheduler runs routines on a daily, weekly, and monthly cadence. Cross-layer handoffs are common — Nova writes a PRD, Apex reviews the architecture, Bolt implements, Lens reviews, Oath verifies.

**This is not a chatbot.** It's an operating layer for your business **and** your engineering team.

## Who It's For

- **Solo founders** who need to run operations without hiring an ops team
- **CEOs of small companies** managing multiple products and communities
- **Small teams** that want automated reporting and coordination
- **Developers** who already use Claude Code and want to extend it

## How It's Different

| Chatbot | EvoNexus |
|---------|------------|
| You ask, it answers | Agents run routines on schedule |
| Forgets between sessions | Persistent memory across sessions |
| One conversation thread | 38 agents with isolated domains (17 business + 21 engineering) |
| Generic helper | Specialized roles per layer: ops, finance, code review, security audit, debugging |
| No integrations | 18+ integrations (Google, GitHub, Stripe, Discord, etc.) |
| Text output | HTML reports, dashboards, structured artifacts |
| Manual every time | Automated daily/weekly/monthly workflows + on-demand pipelines (`dev-autopilot`, `dev-ralplan`) |
| Single LLM persona | Multi-perspective consensus (Planner + Architect + Critic) for high-stakes decisions |

## Key Concepts

### Agents

17 specialized agents, each with a system prompt, slash command, persistent memory, and domain-specific skills:

| Agent | Domain | Command |
|-------|--------|---------|
| Clawdia | Operations — agenda, emails, tasks, decisions | `/clawdia` |
| Flux | Finance — Stripe, ERP, cash flow, reports | `/flux` |
| Atlas | Projects — Linear, GitHub, sprints | `/atlas` |
| Pulse | Community — Discord, WhatsApp, sentiment | `/pulse` |
| Pixel | Social media — content, calendar, analytics | `/pixel` |
| Sage | Strategy — OKRs, roadmap, prioritization | `/sage` |
| Nex | Sales — pipeline, proposals, qualification | `/nex` |
| Mentor | Courses — learning paths, modules | `/mentor` |
| Kai | Personal — health, habits, routine | `/kai` |
| Oracle | Knowledge — workspace docs, how-to, config | `/oracle` |
| Mako | Marketing — campaigns, SEO, brand, content | `/mako` |
| Aria | HR / People — recruiting, onboarding, performance | `/aria` |
| Zara | Customer Success — triage, escalation, health | `/zara` |
| Lex | Legal — contracts, compliance, NDA, risk | `/lex` |
| Nova | Product — specs, roadmaps, metrics, research | `/nova` |
| Dex | Data / BI — analysis, SQL, dashboards | `/dex` |
| Lumen | Learning Retention — spaced repetition (SM-2), fact capture, quizzes | `/lumen-learning` |

### Skills

150+ reusable capabilities organized by prefix (`fin-`, `social-`, `int-`, `prod-`, `hr-`, `legal-`, `ops-`, `cs-`, `data-`, `pm-`, `mkt-`, etc.). Skills are markdown files that teach agents how to perform specific tasks — no plugins, no code.

### Routines

Automated workflows (ADWs) that run on schedule via a Python scheduler. Morning briefings, email triage, financial snapshots, community monitoring, end-of-day consolidation. Each routine logs execution metrics (tokens, cost, duration) in JSONL format.

### Dashboard

A web UI (React + Flask) for managing everything: view reports, start/stop services, browse agents and skills, manage users and roles, and interact with Claude Code through an embedded terminal.

![Web Dashboard](imgs/doc-overview.webp)

### Knowledge Base

Optional semantic search powered by [MemPalace](https://github.com/milla-jovovich/mempalace). Index your project code, documentation, and knowledge for natural-language search — everything runs locally with ChromaDB. Enable it with one click in the Dashboard.

### Memory

Two-tier persistence. `CLAUDE.md` holds working memory (who you are, active projects, key people). The `memory/` directory stores deeper context (people profiles, glossary, project history). Both survive across sessions.

### AI Providers

EvoNexus runs on Anthropic's `claude` CLI by default, but can switch to any of 6 alternate LLM backends (OpenRouter, OpenAI, Gemini, AWS Bedrock, Google Vertex AI, Codex Auth) via [OpenClaude](https://www.npmjs.com/package/@gitlawb/openclaude). The active provider is stored in `config/providers.json` and can be changed from the Providers page in the dashboard — both the terminal-server and the ADW runner re-read the config on every session spawn, so switching takes effect immediately. No vendor lock-in, your choice of model, your keys. See [docs/dashboard/providers.md](dashboard/providers.md) for the full reference.

## Open Source

EvoNexus is MIT-licensed, built by [Evolution Foundation](https://evolutionfoundation.com.br). The source is at [github.com/EvolutionAPI/evo-nexus](https://github.com/EvolutionAPI/evo-nexus). This is an unofficial community project — not affiliated with or endorsed by Anthropic.

It's designed to be forked and adapted. Add your own agents, skills, routines, and integrations. The architecture is markdown-first — no complex plugin systems, just files that Claude Code reads.
