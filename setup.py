#!/usr/bin/env python3
"""
EvoNexus — Setup Wizard
Generates workspace configuration, CLAUDE.md, .env, and folder structure.
Usage: python setup.py  (or: make setup)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent

# ANSI colors
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def banner():
    print(f"""
{GREEN}  ╔══════════════════════════════════╗
  ║   {BOLD}EvoNexus — Setup Wizard{RESET}{GREEN}     ║
  ╚══════════════════════════════════╝{RESET}
""")


def check_prerequisites():
    """Check that required tools are installed before proceeding."""
    errors = []

    # Claude Code CLI
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {GREEN}✓{RESET} Claude Code CLI: {DIM}{version}{RESET}")
        else:
            errors.append("claude")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        errors.append("claude")

    # Python / uv
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {GREEN}✓{RESET} uv: {DIM}{version}{RESET}")
        else:
            errors.append("uv")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        errors.append("uv")

    # Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {GREEN}✓{RESET} Node.js: {DIM}{version}{RESET}")
        else:
            errors.append("node")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        errors.append("node")

    # npm
    npm_cmd = "npm"
    try:
        result = subprocess.run([npm_cmd, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            raise FileNotFoundError
        print(f"  {GREEN}✓{RESET} npm: {DIM}v{result.stdout.strip()}{RESET}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            npm_cmd = "npm.cmd"
            result = subprocess.run([npm_cmd, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"  {GREEN}✓{RESET} npm: {DIM}v{result.stdout.strip()}{RESET}")
            else:
                errors.append("npm")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            errors.append("npm")

    print()

    if errors:
        print(f"  {RED}✗ Missing required tools:{RESET}")
        if "claude" in errors:
            print(f"    {RED}•{RESET} Claude Code CLI — install from {BOLD}https://claude.ai/download{RESET}")
            print(f"      {DIM}npm install -g @anthropic-ai/claude-code{RESET}")
        if "uv" in errors:
            print(f"    {RED}•{RESET} uv (Python package manager) — {BOLD}https://docs.astral.sh/uv/{RESET}")
            print(f"      {DIM}curl -LsSf https://astral.sh/uv/install.sh | sh{RESET}")
        if "node" in errors:
            print(f"    {RED}•{RESET} Node.js 18+ — {BOLD}https://nodejs.org{RESET}")
        if "npm" in errors:
            print(f"    {RED}•{RESET} npm not found (Node.js installed but npm missing from PATH) — {BOLD}https://nodejs.org{RESET}")
        print()
        print(f"  {YELLOW}Install the missing tools and run setup again.{RESET}")
        sys.exit(1)

    return True


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {CYAN}>{RESET} {prompt}{suffix}: ").strip()
    return val or default


def ask_bool(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"  {CYAN}>{RESET} {prompt} {suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "1", "true")


def ask_multi(prompt: str, options: list[dict], defaults: list[str] = None) -> list[str]:
    """Multi-select with checkboxes."""
    if defaults is None:
        defaults = []
    selected = set(defaults)

    print(f"\n  {prompt}")
    for opt in options:
        key = opt["key"]
        label = opt["label"]
        desc = opt.get("desc", "")
        checked = "x" if key in selected else " "
        desc_str = f" — {DIM}{desc}{RESET}" if desc else ""
        print(f"  [{checked}] {label}{desc_str}")

    print(f"\n  {DIM}Enter keys to toggle (comma-separated), or press Enter to accept:{RESET}")
    val = input(f"  {CYAN}>{RESET} ").strip()

    if val:
        for key in val.replace(" ", "").split(","):
            key = key.strip().lower()
            if key in {o["key"] for o in options}:
                if key in selected:
                    selected.discard(key)
                else:
                    selected.add(key)

    return list(selected)


AGENTS = [
    {"key": "ops", "label": "ops", "desc": "Daily operations (briefing, email, tasks)"},
    {"key": "finance", "label": "finance", "desc": "Financial (P&L, cash flow, invoices)"},
    {"key": "projects", "label": "projects", "desc": "Project management (sprints, milestones)"},
    {"key": "community", "label": "community", "desc": "Community (Discord, WhatsApp pulse)"},
    {"key": "social", "label": "social", "desc": "Social media (content, analytics)"},
    {"key": "strategy", "label": "strategy", "desc": "Strategy (OKRs, roadmap)"},
    {"key": "sales", "label": "sales", "desc": "Commercial (pipeline, proposals)"},
    {"key": "courses", "label": "courses", "desc": "Education (course creation)"},
    {"key": "personal", "label": "personal", "desc": "Personal (health, habits)"},
]

INTEGRATIONS = [
    {"key": "google_calendar", "label": "Google Calendar + Gmail"},
    {"key": "todoist", "label": "Todoist"},
    {"key": "discord", "label": "Discord"},
    {"key": "telegram", "label": "Telegram"},
    {"key": "whatsapp", "label": "WhatsApp"},
    {"key": "stripe", "label": "Stripe"},
    {"key": "omie", "label": "Omie ERP"},
    {"key": "github", "label": "GitHub"},
    {"key": "linear", "label": "Linear"},
    {"key": "youtube", "label": "YouTube"},
    {"key": "instagram", "label": "Instagram"},
    {"key": "linkedin", "label": "LinkedIn"},
    {"key": "fathom", "label": "Fathom (meetings)"},
]

DEFAULT_FOLDERS = {
    "daily_logs": "daily-logs",
    "projects": "projects",
    "community": "community",
    "social": "social",
    "finance": "finance",
    "meetings": "meetings",
    "courses": "courses",
    "strategy": "strategy",
}


def generate_workspace_yaml(config: dict) -> str:
    lines = [
        "# EvoNexus Workspace Configuration",
        f"# Generated by setup.py on {config['date']}",
        "",
        f'name: "{config["workspace_name"]}"',
        f'owner: "{config["owner_name"]}"',
        f'company: "{config["company_name"]}"',
        f'timezone: "{config["timezone"]}"',
        f'language: "{config["language"]}"',
        f"port: {config['dashboard_port']}",
        "",
    ]
    return "\n".join(lines)


def generate_claude_md(config: dict) -> str:
    """Generate CLAUDE.md inline — no template file needed."""
    agent_table = ""
    for agent in AGENTS:
        if agent["key"] in config["agents"]:
            agent_table += f"| **{agent['label'].title()}** | `/{agent['key']}` | {agent['desc']} |\n"

    skill_count = len(list((WORKSPACE / ".claude" / "skills").iterdir())) if (WORKSPACE / ".claude" / "skills").is_dir() else 0

    return f"""# {config['workspace_name']} — Claude Context File

Claude reads this file at the start of every session. It's your persistent memory.

---

## How This Workspace Works

This workspace exists to produce things, not just store them. Everything here is oriented around a loop: **define a goal → break it into problems → solve those problems → deliver the output.**

Claude's role is to keep {config['owner_name'].split()[0]} moving through this loop. If there's no goal yet, help define one. If there's a goal but no clear problems, help break it down. If there are problems, help solve the next one. Always push toward the next concrete thing to do or deliver.

---

## Who I Am

**Name:** {config['owner_name']}
**Company:** {config['company_name']}
**Timezone:** {config['timezone']}

---

## Active Projects

| Name | What it is | Status |
|------|---------|--------|
| *(add your projects here)* | | |

---

## Active Agents

| Agent | Command | Domain |
|-------|---------|--------|
{agent_table}
## Skills ({skill_count} skills)

See `.claude/skills/CLAUDE.md` for the complete index.

## What Claude Should Do

- **Always respond in {config['language']}.** This applies to every message, every session, without exception.
- Maintain a professional, clear and well-organized tone.
- Before working on any area, read the corresponding Overview file.
- Outputs for each area go in the correct folder. If unsure, ask.
- When creating files, prefix with [C] to indicate Claude created it.
- Use the correct agents for each domain (see agents table above).
- Use skills with the correct prefix (see `.claude/skills/CLAUDE.md`).

## What Claude Should NOT Do

- Do not edit notes without asking permission. Only files with [C] prefix are free to edit.
- Do not be verbose — be direct and concrete.
- Do not create projects without first interviewing the user about the objective and context.
- Do not overwrite existing skills or templates without confirming.

---

## Memory (Hot Cache)

### Me
{config['owner_name']} — {config['company_name']}

### People
| Who | Role |
|-----|------|
| *(add key people here)* | |
→ Full profiles: memory/people/

### Terms
| Term | Meaning |
|------|---------|
| *(add internal terms here)* | |
→ Full glossary: memory/glossary.md

### Preferences
- Always respond in {config['language']}
- Timezone: {config['timezone']}
- Tone: professional and direct

---

## Memory System

Two-tier memory following the **LLM Wiki pattern** (ingest → query → lint):

- **CLAUDE.md** (this file) — Hot cache with key people, terms, projects (~90% of daily needs)
- **memory/** — Deep storage with full profiles, glossary, project details, trends
  - `index.md` — Centralized catalog of all memory files (auto-updated)
  - `log.md` — Append-only chronological record of all memory operations
  - `glossary.md` — Full decoder ring for internal language
  - `people/` — Complete people profiles
  - `projects/` — Project details and context
  - `context/` — Company, teams, tools

Three operations maintain the knowledge base:
- **Ingest** (daily, memory-sync) — Extracts knowledge and propagates updates across related files
- **Query** (conversations) — Complex syntheses filed back as new entries
- **Lint** (weekly, memory-lint) — Detects contradictions, stale data, orphans, and gaps

---

## Detailed Configuration

See `.claude/rules/` for detailed configuration (auto-loaded by Claude Code):
- `agents.md` — specialized agents and how to use them
- `integrations.md` — MCPs, APIs, GitHub repos, infra and templates
- `routines.md` — daily, weekly and monthly scheduler routines
- `skills.md` — skill categories and prefixes

---

*Claude updates this file as the workspace grows. You can also edit it at any time.*
"""


def copy_env_example(config: dict):
    src = WORKSPACE / ".env.example"
    dst = WORKSPACE / ".env"
    if dst.exists():
        print(f"  {YELLOW}!{RESET} .env already exists, skipping")
        return
    if src.exists():
        shutil.copy2(src, dst)
        print(f"  {GREEN}✓{RESET} Created .env from .env.example")
    else:
        print(f"  {YELLOW}!{RESET} .env.example not found, creating empty .env")
        dst.write_text("# EvoNexus Environment Variables\n# Fill in your API keys below\n\n", encoding="utf-8")


def copy_routines_config(config: dict):
    dst = WORKSPACE / "config" / "routines.yaml"
    if dst.exists():
        print(f"  {YELLOW}!{RESET} config/routines.yaml already exists, skipping")
        return
    # Try example file first, otherwise generate minimal config
    src = WORKSPACE / "config" / "routines.yaml.example"
    if src.exists():
        shutil.copy2(src, dst)
    else:
        dst.write_text("# EvoNexus Routines — edit schedules here\n# See ROUTINES.md for documentation\n\ndaily: []\nweekly: []\nmonthly: []\n", encoding="utf-8")
    print(f"  {GREEN}✓{RESET} Created config/routines.yaml")


def create_folders(config: dict):
    count = 0
    for key, name in config["folders"].items():
        folder = WORKSPACE / name
        folder.mkdir(exist_ok=True)
        gitkeep = folder / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        count += 1

    # Data dirs
    for d in ["data", "memory"]:
        (WORKSPACE / d).mkdir(exist_ok=True)

    print(f"  {GREEN}✓{RESET} Created workspace folders ({count})")


def main():
    banner()

    # Prerequisites check
    print(f"  {BOLD}Checking prerequisites...{RESET}")
    check_prerequisites()

    # Who are you?
    print(f"  {BOLD}About you{RESET}")
    owner_name = ask("Your name", "")
    company_name = ask("Company name", "")
    timezone = ask("Timezone", "America/Sao_Paulo")
    language = ask("Language", "en")
    dashboard_port = int(ask("Dashboard port", "8080"))
    print()

    # All agents and integrations enabled by default
    agents = [a["key"] for a in AGENTS]
    integrations = []  # configured via .env later

    # Build config
    from datetime import date
    config = {
        "date": date.today().isoformat(),
        "workspace_name": f"{company_name or owner_name} Workspace",
        "owner_name": owner_name,
        "company_name": company_name,
        "timezone": timezone,
        "language": language,
        "agents": agents,
        "integrations": integrations,
        "folders": DEFAULT_FOLDERS.copy(),
        "dashboard_port": dashboard_port,
    }

    print(f"  {BOLD}Creating workspace...{RESET}")

    # workspace.yaml
    config_dir = WORKSPACE / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "workspace.yaml").write_text(generate_workspace_yaml(config), encoding="utf-8")
    print(f"  {GREEN}✓{RESET} Generated config/workspace.yaml")

    # .env
    copy_env_example(config)

    # routines.yaml
    copy_routines_config(config)

    # CLAUDE.md
    claude_md = generate_claude_md(config)
    (WORKSPACE / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    print(f"  {GREEN}✓{RESET} Generated CLAUDE.md")

    # Folders
    create_folders(config)

    # Install Python dependencies
    print(f"  {DIM}Installing Python dependencies...{RESET}")
    os.system(f"cd {WORKSPACE} && uv sync -q 2>/dev/null")
    print(f"  {GREEN}✓{RESET} Installed Python dependencies")

    # Dashboard build
    frontend_dir = WORKSPACE / "dashboard" / "frontend"
    if (frontend_dir / "package.json").exists():
        print(f"  {DIM}Building dashboard frontend...{RESET}")
        os.system(f"cd {frontend_dir} && npm install --silent && npm run build --silent 2>/dev/null")
        print(f"  {GREEN}✓{RESET} Built dashboard frontend")

    # Data dir for SQLite
    (WORKSPACE / "dashboard" / "data").mkdir(parents=True, exist_ok=True)

    print(f"""
  {GREEN}Done!{RESET} Next steps:
  1. Edit {BOLD}.env{RESET} with your API keys
  2. Run: {BOLD}make dashboard-app{RESET}
  3. Open {BOLD}http://localhost:{dashboard_port}{RESET} to create your admin account
  4. Run: {BOLD}make scheduler{RESET}    — start automated routines
  5. Run: {BOLD}make help{RESET}         — see all commands

  {YELLOW}Note:{RESET} The admin account is created via the web dashboard,
  not via CLI. This allows us to collect anonymous telemetry
  (geo, version) for the open source project.
""")


if __name__ == "__main__":
    main()
