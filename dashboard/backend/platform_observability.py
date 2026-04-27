from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from flask import current_app

from platform_cache import cache_get_or_set, cache_status
from platform_metrics import summarize_provider_events
from platform_plugins import list_plugins, load_installed_plugins, load_plugin_registry
from platform_queue import list_events, queue_status
from platform_support import WORKSPACE, database_scheme, read_json


def _load_provider_config() -> dict[str, Any]:
    config_path = WORKSPACE / "config" / "providers.json"
    fallback_path = WORKSPACE / "config" / "providers.example.json"
    config = read_json(config_path, read_json(fallback_path, {}))
    return config if isinstance(config, dict) else {}


def _terminal_server_snapshot() -> dict[str, Any]:
    import os

    url = os.environ.get("TERMINAL_SERVER_URL", "http://127.0.0.1:32352").rstrip("/")
    try:
        resp = requests.get(f"{url}/api/health/deep", timeout=3)
        data = resp.json()
        return {
            "status": data.get("status", "warning") if resp.ok else "error",
            "reachable": resp.ok,
            "http_status": resp.status_code,
            "url": url,
            "snapshot": data,
        }
    except Exception as exc:
        return {
            "status": "warning",
            "reachable": False,
            "http_status": None,
            "url": url,
            "error": str(exc)[:200],
        }


def _build_observability_summary() -> dict[str, Any]:
    from routes.health import _build_report
    from routes.costs import costs_summary

    backend_health = _build_report(deep=True)
    terminal = _terminal_server_snapshot()
    costs_resp = costs_summary()
    costs = costs_resp.get_json(silent=True) if hasattr(costs_resp, "get_json") else None
    provider_config = _load_provider_config()
    registry = load_plugin_registry()
    installed = load_installed_plugins()

    provider_metrics = summarize_provider_events(limit=500)
    plugin_list = list_plugins()
    events = list_events(limit=25)

    try:
        database_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    except RuntimeError:
        from runtime_config import database_uri as resolve_database_uri

        database_uri = resolve_database_uri()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": backend_health,
        "terminal_server": terminal,
        "costs": costs or {},
        "provider_config": provider_config,
        "provider_metrics": provider_metrics,
        "cache": cache_status(),
        "queue": queue_status(),
        "plugins": {
            "registry_count": len(registry.get("plugins", [])),
            "installed_count": len(installed.get("plugins", {})),
            "items": plugin_list,
        },
        "recent_events": events,
        "database_backend": database_scheme(database_uri),
    }


def build_observability_summary() -> dict[str, Any]:
    return cache_get_or_set("observability:summary", _build_observability_summary, ttl=30)
