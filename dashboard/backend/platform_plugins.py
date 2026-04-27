from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from platform_queue import publish_event
from platform_support import INSTALLED_PLUGINS_PATH, PLUGIN_REGISTRY_PATH, WORKSPACE, ensure_platform_data_dir, read_json, write_json


_SAFE_PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_AGENTS_DIR = WORKSPACE / ".claude" / "agents"


DEFAULT_PLUGIN_REGISTRY = {
    "plugins": [
        {
            "id": "observability-scout",
            "name": "Observability Scout",
            "version": "1.0.0",
            "category": "observability",
            "description": "Installs a read-only agent pack for platform telemetry and incident triage.",
            "agents": [
                {
                    "name": "observability-scout",
                    "description": "Read-only observability analyst for EvoNexus. Uses metrics, health, costs, and provider routing data to identify regressions.",
                    "model": "haiku",
                    "color": "cyan",
                    "memory": "project",
                    "disallowedTools": ["Write", "Edit", "Bash", "NotebookEdit"],
                    "prompt": (
                        "You are Observability Scout.\n"
                        "Analyze EvoNexus platform health, provider routing, queue/cache status, and cost trends.\n"
                        "Recommend concrete fixes with clear severity. Do not edit files."
                    ),
                }
            ],
        },
        {
            "id": "provider-router",
            "name": "Provider Router",
            "version": "1.0.0",
            "category": "platform",
            "description": "Installs a read-only agent pack for provider failover and routing audits.",
            "agents": [
                {
                    "name": "provider-router",
                    "description": "Read-only provider routing specialist for EvoNexus. Reviews failover order, provider health, and selected model mode.",
                    "model": "haiku",
                    "color": "violet",
                    "memory": "project",
                    "disallowedTools": ["Write", "Edit", "Bash", "NotebookEdit"],
                    "prompt": (
                        "You are Provider Router.\n"
                        "Audit provider health, failover order, and model compatibility.\n"
                        "Recommend a safe routing chain and explain why a fallback should or should not be activated."
                    ),
                }
            ],
        },
    ]
}


def _safe_plugin_id(plugin_id: str) -> str:
    plugin_id = (plugin_id or "").strip().lower()
    if not _SAFE_PLUGIN_ID.match(plugin_id):
        raise ValueError("Invalid plugin id")
    return plugin_id


def load_plugin_registry() -> dict[str, Any]:
    registry = read_json(PLUGIN_REGISTRY_PATH, DEFAULT_PLUGIN_REGISTRY)
    if not isinstance(registry, dict) or "plugins" not in registry:
        return DEFAULT_PLUGIN_REGISTRY
    plugins = registry.get("plugins")
    if not isinstance(plugins, list):
        return DEFAULT_PLUGIN_REGISTRY
    return registry


def load_installed_plugins() -> dict[str, Any]:
    payload = read_json(INSTALLED_PLUGINS_PATH, {"plugins": {}})
    if not isinstance(payload, dict):
        return {"plugins": {}}
    if not isinstance(payload.get("plugins"), dict):
        payload["plugins"] = {}
    return payload


def _save_installed_plugins(payload: dict[str, Any]) -> None:
    ensure_platform_data_dir()
    write_json(INSTALLED_PLUGINS_PATH, payload)


def _render_agent(agent: dict[str, Any], plugin_id: str) -> str:
    frontmatter: dict[str, Any] = {
        "name": agent["name"],
        "description": agent["description"],
        "model": agent.get("model", "haiku"),
        "color": agent.get("color", "cyan"),
        "memory": agent.get("memory", "project"),
        "plugin": plugin_id,
        "disallowedTools": agent.get("disallowedTools", ["Write", "Edit", "Bash", "NotebookEdit"]),
    }
    prompt = agent.get("prompt", "").strip()
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n" + prompt + "\n"


def _installed_files_for(plugin: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for agent in plugin.get("agents", []) or []:
        files.append({
            "type": "agent",
            "name": agent["name"],
            "path": f".claude/agents/{agent['name']}.md",
        })
    return files


def list_plugins() -> list[dict[str, Any]]:
    registry = load_plugin_registry()
    installed = load_installed_plugins().get("plugins", {})
    result = []
    for plugin in registry.get("plugins", []):
        plugin_id = plugin.get("id")
        if not plugin_id:
            continue
        state = installed.get(plugin_id, {})
        result.append({
            **plugin,
            "installed": bool(state),
            "installed_at": state.get("installed_at"),
            "installed_files": state.get("files", []),
        })
    return result


def install_plugin(plugin_id: str, workspace: Path = WORKSPACE) -> dict[str, Any]:
    plugin_key = _safe_plugin_id(plugin_id)
    registry = load_plugin_registry()
    plugin = next((item for item in registry.get("plugins", []) if item.get("id") == plugin_key), None)
    if not plugin:
        raise KeyError(f"Unknown plugin: {plugin_key}")

    installed = load_installed_plugins()
    if plugin_key in installed.get("plugins", {}):
        return installed["plugins"][plugin_key]

    _AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    written_files: list[str] = []
    for agent in plugin.get("agents", []) or []:
        target = workspace / ".claude" / "agents" / f"{agent['name']}.md"
        if target.exists():
            raise FileExistsError(f"Agent file already exists: {target.name}")
        target.write_text(_render_agent(agent, plugin_key), encoding="utf-8")
        written_files.append(str(target.relative_to(workspace)).replace("\\", "/"))

    state = {
        "id": plugin_key,
        "name": plugin.get("name", plugin_key),
        "version": plugin.get("version", "1.0.0"),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": written_files,
    }
    installed.setdefault("plugins", {})[plugin_key] = state
    _save_installed_plugins(installed)
    publish_event("plugin-installed", {"plugin_id": plugin_key, "files": written_files})
    return state


def uninstall_plugin(plugin_id: str, workspace: Path = WORKSPACE) -> dict[str, Any]:
    plugin_key = _safe_plugin_id(plugin_id)
    installed = load_installed_plugins()
    state = installed.get("plugins", {}).get(plugin_key)
    if not state:
        raise KeyError(f"Plugin not installed: {plugin_key}")

    removed: list[str] = []
    for rel_path in state.get("files", []):
        target = workspace / rel_path
        if target.exists():
            target.unlink()
            removed.append(rel_path)

    installed["plugins"].pop(plugin_key, None)
    _save_installed_plugins(installed)
    publish_event("plugin-uninstalled", {"plugin_id": plugin_key, "files": removed})
    return {"id": plugin_key, "removed_files": removed}
