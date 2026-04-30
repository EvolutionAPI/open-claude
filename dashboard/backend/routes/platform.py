from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import login_required

from models import has_permission
from platform_cache import cache_delete, cache_get, cache_get_or_set
from platform_observability import build_observability_summary
from platform_plugins import install_plugin, list_plugins, uninstall_plugin
from platform_queue import list_events, queue_status

bp = Blueprint("platform", __name__)


def _require(resource: str, action: str):
    from flask_login import current_user

    if not has_permission(current_user.role, resource, action):
        return jsonify({"error": "Forbidden"}), 403
    return None


@bp.route("/api/observability/summary")
@login_required
def observability_summary():
    denied = _require("systems", "view")
    if denied:
        return denied
    return jsonify(build_observability_summary())


@bp.route("/api/observability/providers")
@login_required
def observability_providers():
    denied = _require("systems", "view")
    if denied:
        return denied
    def _load_snapshot():
        summary = build_observability_summary()
        return {
            "provider_metrics": summary.get("provider_metrics", {}),
            "provider_config": summary.get("provider_config", {}),
        }

    return jsonify(cache_get_or_set("observability:providers", _load_snapshot, ttl=30))


@bp.route("/api/platform/cache")
@login_required
def platform_cache():
    denied = _require("systems", "view")
    if denied:
        return denied
    return jsonify({
        "cached_provider_list": cache_get("providers:list"),
        "cached_observability": cache_get("observability:summary"),
        "cached_observability_providers": cache_get("observability:providers"),
        "cached_platform_queue": cache_get("platform:queue:50"),
    })


@bp.route("/api/platform/cache/clear", methods=["POST"])
@login_required
def platform_cache_clear():
    denied = _require("config", "manage")
    if denied:
        return denied
    cache_delete("providers:list")
    cache_delete("observability:summary")
    cache_delete("observability:providers")
    cache_delete("platform:queue:50")
    return jsonify({"status": "ok"})


@bp.route("/api/platform/queue")
@login_required
def platform_queue():
    denied = _require("systems", "view")
    if denied:
        return denied
    return jsonify(cache_get_or_set(
        "platform:queue:50",
        lambda: {
            "status": queue_status(),
            "events": list_events(limit=50),
        },
        ttl=10,
    ))


@bp.route("/api/platform/plugins")
@login_required
def plugins_list():
    denied = _require("systems", "view")
    if denied:
        return denied
    return jsonify({"plugins": list_plugins()})


@bp.route("/api/platform/plugins/install", methods=["POST"])
@login_required
def plugins_install():
    denied = _require("config", "manage")
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    plugin_id = (data.get("plugin_id") or "").strip()
    if not plugin_id:
        return jsonify({"error": "plugin_id is required"}), 400
    try:
        result = install_plugin(plugin_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except FileExistsError as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    cache_delete("observability:summary")
    return jsonify({"status": "ok", "plugin": result})


@bp.route("/api/platform/plugins/<plugin_id>/uninstall", methods=["POST"])
@login_required
def plugins_uninstall(plugin_id: str):
    denied = _require("config", "manage")
    if denied:
        return denied
    try:
        result = uninstall_plugin(plugin_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    cache_delete("observability:summary")
    return jsonify({"status": "ok", "plugin": result})
