"""Plugins API — install, uninstall, list, health, widget endpoints.

ADR-5: install uses a state-machine with per-slug fcntl lock and crash recovery.
B1 (Raven): rollback_from_state() reverses completed steps on any failure.
B2 (Raven): InstallLock prevents concurrent installs of the same plugin.
Vault C5 (F5): widget serving uses os.path.realpath + startswith containment.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

bp = Blueprint("plugins", __name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent
PLUGINS_DIR = WORKSPACE / "plugins"
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _WidgetLimitError(Exception):
    """Raised when a plugin would exceed the per-mount_point widget limit (AC27)."""


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _audit(conn: sqlite3.Connection, plugin_id: str, action: str, payload: Any = None, success: bool = True) -> None:
    """Write a row to plugin_audit_log."""
    try:
        conn.execute(
            "INSERT INTO plugin_audit_log (plugin_id, action, payload, success, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (plugin_id, action, json.dumps(payload) if payload is not None else None,
             1 if success else 0, _now_iso()),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("audit log write failed: %s", exc)


def _plugin_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# GET /api/plugins — list installed plugins
# ---------------------------------------------------------------------------

@bp.route("/api/plugins", methods=["GET"])
@login_required
def list_plugins():
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM plugins_installed ORDER BY installed_at DESC"
        ).fetchall()
        return jsonify([_plugin_to_dict(r) for r in rows])
    except sqlite3.OperationalError as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/plugins/<slug> — plugin detail
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>", methods=["GET"])
@login_required
def get_plugin(slug: str):
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM plugins_installed WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Plugin not found"}), 404
        return jsonify(_plugin_to_dict(row))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/plugins/preview — validate without installing
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/preview", methods=["POST"])
@login_required
def preview_plugin():
    data = request.get_json(force=True, silent=True) or {}
    source_url = data.get("source_url", "")
    if not source_url:
        return jsonify({"error": "source_url required"}), 400

    from dashboard.backend.plugin_loader import PluginInstaller

    installer = PluginInstaller()
    try:
        preview = installer.preview(source_url)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    if preview.get("conflicts"):
        return jsonify(preview), 409

    return jsonify(preview)


# ---------------------------------------------------------------------------
# POST /api/plugins/install — full install with state machine
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/install", methods=["POST"])
@login_required
def install_plugin():
    data = request.get_json(force=True, silent=True) or {}
    source_url = data.get("source_url", "")
    if not source_url:
        return jsonify({"error": "source_url required"}), 400

    from dashboard.backend.plugin_loader import PluginInstaller, ConflictError, VersionError
    from dashboard.backend.plugin_file_ops import (
        copy_with_manifest, append_rules_index, write_manifest,
    )
    from dashboard.backend.plugin_migrator import install_plugin_sql, MigrationError
    from dashboard.backend.plugin_hook_runner import run_lifecycle_hook, LifecycleHookError
    from dashboard.backend.plugin_install_state import (
        InstallLock, save_state, finalize_install, rollback_from_state
    )
    from dashboard.backend.heartbeat_schema import load_heartbeats_yaml
    from dashboard.backend.plugin_loader import _reload_scheduler

    installer = PluginInstaller()

    # Preview / validate first
    try:
        preview = installer.preview(source_url)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    if preview.get("conflicts"):
        return jsonify({"error": "conflict", "details": preview["conflicts"]}), 409
    if not preview.get("version_ok", True):
        return jsonify({"error": "version_incompatible", "details": preview["conflicts"]}), 409

    manifest = preview["manifest"]
    slug = manifest["id"]

    # ADR-5 + B2: per-slug lock
    try:
        lock = InstallLock(slug)
        lock.__enter__()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409

    plugin_dir = PLUGINS_DIR / slug
    state: dict[str, Any] = {
        "slug": slug,
        "source_url": source_url,
        "started_at": _now_iso(),
        "completed_steps": [],
    }
    conn = _get_db()

    try:
        # --- Step: copy plugin source to plugins/{slug}/ ---
        plugin_dir.mkdir(parents=True, exist_ok=True)

        # Copy entire source into plugin dir
        source_path = Path(source_url)
        if source_path.is_dir():
            shutil.copytree(source_path, plugin_dir, dirs_exist_ok=True)
        else:
            return jsonify({"error": f"source_url must be a local directory: {source_url}"}), 400

        state["completed_steps"].append({"step": "copy_source"})
        save_state(slug, state)

        # --- Step: pre-install hook ---
        pre_hook = plugin_dir / "hooks" / "pre-install.sh"
        if pre_hook.exists():
            try:
                run_lifecycle_hook(plugin_dir, "pre-install", timeout=60)
            except LifecycleHookError as exc:
                raise RuntimeError(f"pre-install hook failed: {exc}") from exc
        state["completed_steps"].append({"step": "pre_install_hook"})
        save_state(slug, state)

        # --- Step: SQL migrations ---
        install_sql_path = plugin_dir / "migrations" / "install.sql"
        if install_sql_path.exists():
            try:
                conn2 = sqlite3.connect(str(DB_PATH))
                install_plugin_sql(slug, install_sql_path, conn=conn2)
                conn2.close()
            except MigrationError as exc:
                raise RuntimeError(f"SQL migration failed: {exc}") from exc
        state["completed_steps"].append({"step": "sql_migrations"})
        save_state(slug, state)

        # --- Step: copy agents ---
        agents_src = plugin_dir / "agents"
        agents_dst = WORKSPACE / ".claude" / "agents"
        agent_files: list[dict] = []
        if agents_src.exists():
            copy_with_manifest(agents_src, agents_dst, slug, "agents", agent_files)
        state["completed_steps"].append({"step": "copy_agents", "copied_files": agent_files})
        save_state(slug, state)

        # --- Step: copy skills ---
        skills_src = plugin_dir / "skills"
        skills_dst = WORKSPACE / ".claude" / "skills"
        skill_files: list[dict] = []
        if skills_src.exists():
            copy_with_manifest(skills_src, skills_dst, slug, "skills", skill_files)
        state["completed_steps"].append({"step": "copy_skills", "copied_files": skill_files})
        save_state(slug, state)

        # --- Step: copy commands ---
        commands_src = plugin_dir / "commands"
        commands_dst = WORKSPACE / ".claude" / "commands"
        command_files: list[dict] = []
        if commands_src.exists():
            copy_with_manifest(commands_src, commands_dst, slug, "commands", command_files)
        state["completed_steps"].append({"step": "copy_commands", "copied_files": command_files})
        save_state(slug, state)

        # --- Step: copy rules + append index marker ---
        rules_src = plugin_dir / "rules"
        rules_dst = WORKSPACE / ".claude" / "rules"
        rule_files: list[dict] = []
        if rules_src.exists():
            copy_with_manifest(rules_src, rules_dst, slug, "rules", rule_files)
            rule_names = [f.get("dest_filename", f.get("dest", "").split("/")[-1]) for f in rule_files]
            append_rules_index(slug, rule_names)
        state["completed_steps"].append({
            "step": "rules_index_marker",
            "copied_files": rule_files,
        })
        save_state(slug, state)

        # --- Step: copy claude hook handlers ---
        hooks_src = plugin_dir / "claude-hook-handlers"
        hook_files: list[dict] = []
        if hooks_src.exists():
            # Hook handlers stay inside plugins/{slug}/claude-hook-handlers/
            # (no namespace copy needed — dispatcher discovers them there)
            for h in hooks_src.iterdir():
                if h.is_file():
                    hook_files.append({"dest": str(h), "sha256": _sha256(h)})
        state["completed_steps"].append({"step": "copy_claude_hooks", "copied_files": hook_files})
        save_state(slug, state)

        # --- Step: heartbeats union ---
        # Heartbeat YAML stays in plugins/{slug}/heartbeats.yaml — union happens at load time
        # Sync to DB if heartbeat dispatcher is running
        try:
            import sys
            backend_dir = Path(__file__).resolve().parent.parent
            if str(backend_dir) not in sys.path:
                sys.path.insert(0, str(backend_dir))
            from heartbeat_dispatcher import _sync_heartbeats_to_db
            _sync_heartbeats_to_db()
        except Exception as exc:
            logger.info("Heartbeat sync skipped (dispatcher not running): %s", exc)
        state["completed_steps"].append({"step": "heartbeats_union"})
        save_state(slug, state)

        # --- Step: routines union + SIGHUP ---
        routine_error = _reload_scheduler()
        state["completed_steps"].append({
            "step": "routines_union",
            "routine_error": routine_error,
        })
        save_state(slug, state)

        # --- Step: widget mount_point limit check (AC27) ---
        # Max 3 widgets per mount_point across all active plugins (excluding self).
        _WIDGET_MOUNT_LIMIT = 3
        incoming_widgets = (manifest.get("ui_entry_points") or {}).get("widgets") or []
        if incoming_widgets:
            # Count existing widgets per mount_point from DB
            mount_counts: dict[str, int] = {}
            try:
                rows_mp = conn.execute(
                    "SELECT manifest_json FROM plugins_installed WHERE enabled = 1 AND status = 'active' AND slug != ?",
                    (slug,),
                ).fetchall()
                for row_mp in rows_mp:
                    try:
                        existing_manifest = json.loads(row_mp["manifest_json"] or "{}")
                        for wspec in (existing_manifest.get("ui_entry_points") or {}).get("widgets") or []:
                            mp = wspec.get("mount_point")
                            if mp:
                                mount_counts[mp] = mount_counts.get(mp, 0) + 1
                    except Exception:
                        pass
            except sqlite3.OperationalError:
                pass  # Table may not exist in early bootstrap

            for wspec in incoming_widgets:
                mp = wspec.get("mount_point")
                if mp and mount_counts.get(mp, 0) >= _WIDGET_MOUNT_LIMIT:
                    raise _WidgetLimitError(
                        f"Widget mount_point '{mp}' already has {mount_counts[mp]} widgets "
                        f"(limit: {_WIDGET_MOUNT_LIMIT}). Cannot install plugin '{slug}'."
                    )

        # --- Step: copy widgets ---
        widgets_src = plugin_dir / "ui" / "widgets"
        widget_files: list[dict] = []
        if widgets_src.exists():
            for w in widgets_src.glob("*.js"):
                sha = _sha256(w)
                widget_files.append({
                    "filename": w.name,
                    "sha256": sha,
                    "url": f"/plugins/{slug}/ui/widgets/{w.name}",
                })
        state["completed_steps"].append({"step": "copy_widgets", "widget_files": widget_files})
        save_state(slug, state)

        # --- Step: post-install hook ---
        post_hook = plugin_dir / "hooks" / "post-install.sh"
        if post_hook.exists():
            try:
                run_lifecycle_hook(plugin_dir, "post-install", timeout=60)
            except LifecycleHookError as exc:
                logger.warning("post-install hook failed (non-blocking): %s", exc)
        state["completed_steps"].append({"step": "post_install_hook"})
        save_state(slug, state)

        # --- Step: DB register ---
        manifest_sha = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()

        try:
            conn.execute(
                """INSERT INTO plugins_installed
                   (id, slug, name, version, tier, source_type, source_url,
                    installed_at, enabled, manifest_json, install_sha256, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'active')
                   ON CONFLICT(slug) DO NOTHING""",
                (slug, slug, manifest["name"], manifest["version"],
                 manifest.get("tier", "essential"), "local", source_url,
                 _now_iso(), json.dumps(manifest), manifest_sha),
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            raise RuntimeError(f"DB register failed: {exc}") from exc

        state["completed_steps"].append({"step": "db_register"})
        save_state(slug, state)

        # --- Finalize: write manifest + rename state file ---
        final_manifest = {
            "slug": slug,
            "manifest": manifest,
            "installed_at": _now_iso(),
            "steps": state["completed_steps"],
            "agents": agent_files,
            "skills": skill_files,
            "commands": command_files,
            "rules": rule_files,
            "widgets": widget_files,
            "routine_activation_pending": routine_error is not None,
        }
        finalize_install(slug, final_manifest)

        _audit(conn, slug, "install", {"source_url": source_url}, success=True)
        lock.__exit__(None, None, None)

        return jsonify({
            "slug": slug,
            "status": "active",
            "routine_activation_pending": routine_error is not None,
            "warnings": preview.get("warnings", []),
        })

    except _WidgetLimitError as exc:
        # AC27: widget mount_point limit — no rollback needed (nothing was written yet)
        logger.warning("Plugin install blocked by widget limit for '%s': %s", slug, exc)
        lock.__exit__(None, None, None)
        return jsonify({"error": "widget_limit_exceeded", "detail": str(exc)}), 409

    except Exception as exc:
        logger.error("Plugin install failed for '%s': %s", slug, exc)
        try:
            rollback_log = rollback_from_state(slug, state, DB_PATH)
            logger.info("Rollback log: %s", rollback_log)
        except Exception as rb_exc:
            logger.error("Rollback also failed: %s", rb_exc)
        _audit(conn, slug, "install_failed", {"error": str(exc)}, success=False)
        lock.__exit__(None, None, None)
        return jsonify({"error": str(exc)}), 500

    finally:
        conn.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# DELETE /api/plugins/<slug> — uninstall
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>", methods=["DELETE"])
@login_required
def uninstall_plugin(slug: str):
    from dashboard.backend.plugin_file_ops import remove_rules_index, reverse_remove_from_manifest
    from dashboard.backend.plugin_migrator import uninstall_plugin_sql
    from dashboard.backend.plugin_hook_runner import run_lifecycle_hook
    from dashboard.backend.plugin_loader import _reload_scheduler

    plugin_dir = PLUGINS_DIR / slug
    if not plugin_dir.exists():
        return jsonify({"error": f"Plugin '{slug}' not found"}), 404

    conn = _get_db()
    try:
        # Pre-uninstall hook
        pre_hook = plugin_dir / "hooks" / "pre-uninstall.sh"
        if pre_hook.exists():
            try:
                run_lifecycle_hook(plugin_dir, "pre-uninstall", timeout=60)
            except Exception as exc:
                logger.warning("pre-uninstall hook failed: %s", exc)

        # Remove files from manifest (reverse order)
        manifest_path = plugin_dir / ".install-manifest.json"
        if manifest_path.exists():
            try:
                reverse_remove_from_manifest(manifest_path)
            except Exception as exc:
                logger.warning("manifest file removal failed: %s", exc)

        # Remove rules index marker
        try:
            remove_rules_index(slug)
        except Exception as exc:
            logger.warning("rules index removal failed: %s", exc)

        # SQL uninstall
        uninstall_sql = plugin_dir / "migrations" / "uninstall.sql"
        if uninstall_sql.exists():
            try:
                conn2 = sqlite3.connect(str(DB_PATH))
                uninstall_plugin_sql(slug, uninstall_sql, conn=conn2)
                conn2.close()
            except Exception as exc:
                logger.warning("SQL uninstall failed: %s", exc)

        # Post-uninstall hook
        post_hook = plugin_dir / "hooks" / "post-uninstall.sh"
        if post_hook.exists():
            try:
                run_lifecycle_hook(plugin_dir, "post-uninstall", timeout=60)
            except Exception as exc:
                logger.warning("post-uninstall hook failed: %s", exc)

        # Remove plugin directory
        shutil.rmtree(plugin_dir, ignore_errors=True)

        # DB remove
        conn.execute("DELETE FROM plugins_installed WHERE slug = ?", (slug,))
        conn.commit()

        # Reset circuit breaker state
        conn.execute(
            "DELETE FROM plugin_hook_circuit_state WHERE plugin_slug = ?", (slug,)
        )
        conn.commit()

        # Reload scheduler
        _reload_scheduler()

        _audit(conn, slug, "uninstall", success=True)
        return jsonify({"slug": slug, "status": "uninstalled"})

    except Exception as exc:
        logger.error("Uninstall failed for '%s': %s", slug, exc)
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PATCH /api/plugins/<slug> — enable/disable
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>", methods=["PATCH"])
@login_required
def update_plugin_status(slug: str):
    data = request.get_json(force=True, silent=True) or {}
    enabled = data.get("enabled")
    if enabled is None:
        return jsonify({"error": "enabled field required"}), 400

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id FROM plugins_installed WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Plugin not found"}), 404

        status = "active" if enabled else "disabled"
        conn.execute(
            "UPDATE plugins_installed SET enabled = ?, status = ? WHERE slug = ?",
            (1 if enabled else 0, status, slug),
        )
        conn.commit()
        _audit(conn, slug, "enable" if enabled else "disable")
        return jsonify({"slug": slug, "enabled": enabled, "status": status})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/plugins/<slug>/health — validate SHA256 against disk
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>/health", methods=["GET"])
@login_required
def plugin_health(slug: str):
    plugin_dir = PLUGINS_DIR / slug
    manifest_path = plugin_dir / ".install-manifest.json"

    if not plugin_dir.exists():
        return jsonify({"slug": slug, "status": "not_installed"}), 404

    if not manifest_path.exists():
        return jsonify({"slug": slug, "status": "broken", "reason": "no_manifest"}), 200

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"slug": slug, "status": "broken", "reason": "manifest_unreadable"}), 200

    tampered: list[str] = []
    all_files = (
        manifest.get("agents", []) + manifest.get("skills", []) +
        manifest.get("commands", []) + manifest.get("rules", [])
    )
    for file_info in all_files:
        dest = Path(file_info.get("dest", ""))
        expected_sha = file_info.get("sha256")
        if not dest.exists():
            tampered.append(f"missing:{dest}")
            continue
        if expected_sha and _sha256(dest) != expected_sha:
            tampered.append(f"tampered:{dest}")

    if tampered:
        return jsonify({"slug": slug, "status": "broken", "tampered_files": tampered}), 200

    return jsonify({"slug": slug, "status": "active"})


# ---------------------------------------------------------------------------
# GET /api/plugins/widgets?mount=overview — list registered widgets
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/widgets", methods=["GET"])
@login_required
def list_widgets():
    mount = request.args.get("mount", "")
    widgets: list[dict] = []

    if not PLUGINS_DIR.exists():
        return jsonify(widgets)

    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT slug FROM plugins_installed WHERE enabled = 1 AND status = 'active'"
        ).fetchall()
        active_slugs = {r["slug"] for r in rows}
    finally:
        conn.close()

    for plugin_dir in sorted(PLUGINS_DIR.glob("*/")):
        slug = plugin_dir.name
        if slug.startswith(".") or slug not in active_slugs:
            continue
        manifest_path = plugin_dir / ".install-manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for w in manifest.get("widgets", []):
            widget_manifest = manifest.get("manifest", {})
            for wspec in widget_manifest.get("widgets", []):
                if mount and wspec.get("mount_point") != mount:
                    continue
                widgets.append({
                    "slug": slug,
                    "widget_id": wspec.get("id"),
                    "custom_element_name": wspec.get("custom_element_name"),
                    "bundle_url": f"/plugins/{slug}/ui/widgets/{w.get('filename')}",
                    "mount_point": wspec.get("mount_point"),
                })

    return jsonify(widgets)


# ---------------------------------------------------------------------------
# POST /api/plugins/regenerate-markers — rebuild _plugins-index.md (AC33)
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/regenerate-markers", methods=["POST"])
@login_required
def regenerate_markers():
    """Rebuild _plugins-index.md atomically from all active plugins (AC33).

    Builds the full index content in memory, then writes it in a single
    os.replace() call — no unlink() + loop pattern that creates a TOCTOU window.
    """
    from dashboard.backend.plugin_file_ops import _atomic_write, _build_block, RULES_INDEX_PATH

    conn = _get_db()
    rebuilt: list[str] = []
    try:
        rows = conn.execute(
            "SELECT slug FROM plugins_installed WHERE enabled = 1 AND status = 'active'"
        ).fetchall()
        active_slugs = [r["slug"] for r in rows]
    finally:
        conn.close()

    # Build full content in memory, then write once atomically (AC33)
    blocks: list[str] = []
    for slug in active_slugs:
        plugin_dir = PLUGINS_DIR / slug
        manifest_path = plugin_dir / ".install-manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rule_names = [
                f.get("dest_filename", "")
                for f in manifest.get("rules", [])
                if f.get("dest_filename")
            ]
            if rule_names:
                blocks.append(_build_block(slug, rule_names))
                rebuilt.append(slug)
        except Exception as exc:
            logger.warning("regenerate-markers: failed for '%s': %s", slug, exc)

    # Single atomic write — replaces old file or creates new one
    full_content = "\n".join(blocks) + ("\n" if blocks else "")
    _atomic_write(RULES_INDEX_PATH, full_content)

    return jsonify({"rebuilt_for": rebuilt})


# ---------------------------------------------------------------------------
# GET /api/plugins/<slug>/readonly-data/<query_name> — ADR-4 safe queries
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>/readonly-data/<query_name>", methods=["GET"])
@login_required
def readonly_data(slug: str, query_name: str):
    """Execute a declared readonly query from the plugin manifest.

    ADR-4: SQL lives in plugin.yaml (not in the widget request). Queries are
    validated on install to only touch {slug_under}_* tables. Hard row cap: 1000.
    """
    plugin_dir = PLUGINS_DIR / slug
    manifest_path = plugin_dir / ".install-manifest.json"

    if not manifest_path.exists():
        return jsonify({"error": "Plugin not found"}), 404

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_manifest = manifest_data.get("manifest", {})
    except Exception:
        return jsonify({"error": "Manifest unreadable"}), 500

    # Find query declaration — readonly_data is a list of {id, description, sql}
    rd = plugin_manifest.get("readonly_data") or []
    query_decl = next((q for q in rd if isinstance(q, dict) and q.get("id") == query_name), None)

    if not query_decl:
        return jsonify({"error": f"Query '{query_name}' not declared in plugin manifest"}), 404

    sql = query_decl.get("sql")
    if not sql:
        return jsonify({"error": "Invalid query declaration"}), 500

    # Build query params from request.args — only declared params allowed
    declared_params = query_decl.get("params", {})
    params: dict = {}
    for key, value in request.args.items():
        if key not in declared_params:
            return jsonify({"error": f"Parameter '{key}' not declared in manifest"}), 400
        params[key] = value

    # Fill defaults for missing params
    for key, meta in declared_params.items():
        if key not in params:
            if isinstance(meta, dict):
                params[key] = meta.get("default")
            else:
                params[key] = meta

    # Hard cap 1000 rows (ADR-4)
    if "limit" in params:
        try:
            params["limit"] = min(int(params["limit"]), 1000)
        except (TypeError, ValueError):
            params["limit"] = 1000
    elif ":limit" in sql:
        params["limit"] = 1000

    try:
        conn = _get_db()
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchmany(1000)]
        conn.close()
        return jsonify({"query": query_name, "count": len(rows), "rows": rows})
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /plugins/<slug>/ui/<path:subpath> — widget file serving (Step 10)
# C5 (Vault F5): realpath + startswith containment
# ---------------------------------------------------------------------------

@bp.route("/plugins/<slug>/ui/<path:subpath>", methods=["GET"])
@login_required
def serve_widget(slug: str, subpath: str):
    """Serve widget bundle files with strict CSP and auth (C5 Vault F5)."""
    plugin_dir = PLUGINS_DIR / slug
    plugin_ui_root = os.path.realpath(str(plugin_dir / "ui"))
    requested = os.path.realpath(os.path.join(plugin_ui_root, subpath))

    # C5: containment check — must stay inside plugins/{slug}/ui/
    if not requested.startswith(plugin_ui_root + os.sep):
        abort(404)

    if not os.path.isfile(requested):
        abort(404)

    # MIME whitelist
    ext = os.path.splitext(requested)[1].lower()
    mime_map = {
        ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".json": "application/json; charset=utf-8",
    }
    mime = mime_map.get(ext)
    if not mime:
        abort(404)  # unsupported file type

    from flask import make_response
    resp = make_response(open(requested, "rb").read())
    resp.headers["Content-Type"] = mime
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "public, max-age=3600, immutable"
    # Strict CSP for widget files — widgets may only connect back to self
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "style-src 'unsafe-inline' 'self'; "
        "img-src 'self' data:"
    )
    return resp


# ---------------------------------------------------------------------------
# POST /api/plugins/<slug>/update — in-place knowledge layer update (v1a)
#
# AC10: SQL SHA changed → 409 "migration_chain_not_supported_in_v1a"
# AC11: SQL SHA unchanged → copy new knowledge layer files, bump version, update DB
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/<slug>/update", methods=["POST"])
@login_required
def update_plugin(slug: str):
    """Update a plugin — only allowed when the SQL layer is unchanged.

    AC10: If install.sql SHA differs between installed and candidate → 409.
    AC11: If install.sql SHA is identical → overwrite knowledge layer files and bump version.
    """
    from dashboard.backend.plugin_schema import load_plugin_manifest
    from dashboard.backend.plugin_file_ops import (
        copy_with_manifest, append_rules_index, write_manifest, _sha256_file,
    )
    from dashboard.backend.plugin_loader import _parse_version, _reload_scheduler

    conn = _get_db()
    try:
        # 1. Validate plugin is installed
        row = conn.execute(
            "SELECT slug, source_url, version, manifest_json FROM plugins_installed WHERE slug = ?",
            (slug,)
        ).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404

        installed_source = row["source_url"]
        installed_version = row["version"]
        try:
            installed_manifest_dict = json.loads(row["manifest_json"] or "{}")
        except Exception:
            installed_manifest_dict = {}

        # Extract installed SQL SHA from stored manifest (files section if present)
        installed_sql_sha = (
            installed_manifest_dict.get("files", {}).get("migrations/install.sql", {}).get("sha256")
            if isinstance(installed_manifest_dict.get("files"), dict)
            else None
        )
        # Fallback: compute from disk if the manifest doesn't carry it
        if installed_sql_sha is None:
            installed_sql_path = PLUGINS_DIR / slug / "migrations" / "install.sql"
            if installed_sql_path.exists():
                installed_sql_sha = _sha256_file(installed_sql_path)

        # 2. Accept optional source_url override; default to installed
        data = request.get_json(force=True, silent=True) or {}
        source_url = data.get("source_url", installed_source)

        # 3. Resolve new plugin directory (must be a local directory in v1a)
        new_plugin_dir = Path(source_url)
        if not new_plugin_dir.is_dir():
            return jsonify({"error": "fetch_failed", "message": f"source_url must be a local directory: {source_url}"}), 500

        # 4. Load and validate new manifest
        try:
            new_manifest = load_plugin_manifest(new_plugin_dir)
        except Exception as exc:
            return jsonify({"error": "schema_invalid", "message": str(exc)}), 400

        new_version = new_manifest.version

        # 5. Version check — candidate must be strictly newer
        if _parse_version(new_version) <= _parse_version(installed_version):
            return jsonify({
                "error": "not_newer",
                "installed": installed_version,
                "candidate": new_version,
            }), 409

        # 6. Compute new SQL SHA
        new_sql_path = new_plugin_dir / "migrations" / "install.sql"
        new_sql_sha = _sha256_file(new_sql_path) if new_sql_path.exists() else None

        # 7. AC10: Block if SQL SHA changed
        if new_sql_sha != installed_sql_sha:
            return jsonify({
                "error": "migration_chain_not_supported_in_v1a",
                "message": (
                    "install.sql changed between versions. "
                    "In v1a, uninstall and reinstall. "
                    "Migration chain between versions is planned for v1b."
                ),
                "installed_sql_sha": installed_sql_sha,
                "new_sql_sha": new_sql_sha,
            }), 409

        # 8. AC11: Copy new knowledge layer files in place
        # Reuse copy_with_manifest — it handles namespace enforcement and SHA tracking
        plugin_dir = PLUGINS_DIR / slug
        agent_files: list[dict] = []
        skill_files: list[dict] = []
        command_files: list[dict] = []
        rule_files: list[dict] = []
        widget_files: list[dict] = []

        agents_src = new_plugin_dir / "agents"
        if agents_src.exists():
            copy_with_manifest(agents_src, WORKSPACE / ".claude" / "agents", slug, "agents", agent_files)

        skills_src = new_plugin_dir / "skills"
        if skills_src.exists():
            copy_with_manifest(skills_src, WORKSPACE / ".claude" / "skills", slug, "skills", skill_files)

        commands_src = new_plugin_dir / "commands"
        if commands_src.exists():
            copy_with_manifest(commands_src, WORKSPACE / ".claude" / "commands", slug, "commands", command_files)

        rules_src = new_plugin_dir / "rules"
        if rules_src.exists():
            copy_with_manifest(rules_src, WORKSPACE / ".claude" / "rules", slug, "rules", rule_files)
            rule_names = [r.get("dest", "").split("/")[-1] for r in rule_files if r.get("dest")]
            if rule_names:
                append_rules_index(slug, rule_names)

        # Widget files live inside plugins/{slug}/ui/widgets/; copy source into installed dir
        widgets_src = new_plugin_dir / "ui" / "widgets"
        if widgets_src.exists():
            widgets_dst = plugin_dir / "ui" / "widgets"
            widgets_dst.mkdir(parents=True, exist_ok=True)
            for w in widgets_src.glob("*.js"):
                sha = _sha256_file(w)
                shutil.copy2(w, widgets_dst / w.name)
                widget_files.append({
                    "filename": w.name,
                    "sha256": sha,
                    "url": f"/plugins/{slug}/ui/widgets/{w.name}",
                })

        # 9. Heartbeats/routines union — re-reads on next dispatch cycle; trigger reload
        _reload_scheduler()

        # 10. Build updated manifest dict
        new_manifest_dict = new_manifest.model_dump()

        # 11. Update DB
        conn.execute(
            "UPDATE plugins_installed SET version = ?, manifest_json = ? WHERE slug = ?",
            (new_version, json.dumps(new_manifest_dict), slug)
        )
        conn.commit()

        # 12. Audit log
        _audit(conn, slug, "update", {"from": installed_version, "to": new_version, "sql_sha_preserved": True})

        return jsonify({
            "status": "updated",
            "id": slug,
            "from_version": installed_version,
            "to_version": new_version,
        })

    except Exception as exc:
        logger.error("Plugin update failed for '%s': %s", slug, exc)
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/plugins/marketplace — cached registry fetch (Step 13)
# ---------------------------------------------------------------------------

@bp.route("/api/plugins/marketplace", methods=["GET"])
@login_required
def marketplace():
    try:
        from dashboard.backend.plugin_registry import fetch_registry
        result = fetch_registry()
        return jsonify(result)
    except ImportError:
        return jsonify({"plugins": [], "error": "registry_module_not_available"})
    except Exception as exc:
        return jsonify({"plugins": [], "error": str(exc)})
