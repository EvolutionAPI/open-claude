"""Flask backend for the workspace dashboard — EvoNexus."""

import os
import sys
import secrets
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from flask_login import LoginManager, current_user

# Workspace root: two levels up from backend/
WORKSPACE = Path(__file__).resolve().parent.parent.parent

# Load .env from workspace root
load_dotenv(WORKSPACE / ".env")

# Add social-auth to path
sys.path.insert(0, str(WORKSPACE / "social-auth"))

app = Flask(__name__, static_folder=None)
# Persist secret key so sessions survive restarts
_secret_key = os.environ.get("EVONEXUS_SECRET_KEY")
if not _secret_key:
    _key_file = WORKSPACE / "dashboard" / "data" / ".secret_key"
    _key_file.parent.mkdir(parents=True, exist_ok=True)
    if _key_file.exists():
        _secret_key = _key_file.read_text().strip()
    else:
        _secret_key = secrets.token_hex(32)
        _key_file.write_text(_secret_key)
        _key_file.chmod(0o600)

app.secret_key = _secret_key
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{WORKSPACE / 'dashboard' / 'data' / 'evonexus.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
CORS(app, origins=["http://localhost:5173"], supports_credentials=True)

# --------------- Database ---------------
from models import db, User, needs_setup, seed_roles, seed_systems
db.init_app(app)

# Create tables on first run + enable WAL mode for concurrent reads
with app.app_context():
    db.create_all()
    db.session.execute(db.text("PRAGMA journal_mode=WAL"))
    db.session.commit()
    seed_roles()
    seed_systems()
    # Sync trigger definitions from YAML config
    from routes.triggers import sync_triggers_from_yaml
    sync_triggers_from_yaml()

# --------------- Licensing (register-only, no heartbeat) ───
from licensing import auto_register_if_needed

with app.app_context():
    auto_register_if_needed()

# --------------- Login Manager ---------------
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Authentication required"}), 401

# --------------- Auth Middleware ---------------
PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/needs-setup",
    "/api/auth/setup",
    "/api/config/workspace-status",
    "/api/version",
    "/api/version/check",
    "/api/agents/active",
}

@app.before_request
def auth_middleware():
    path = request.path

    # Static assets and frontend
    if not path.startswith("/api/") and not path.startswith("/ws/"):
        return None

    # WebSocket — auth checked inside the handler
    if path.startswith("/ws/"):
        return None

    # Public API paths (exact match or prefix match for docs/webhooks)
    if path in PUBLIC_PATHS or path.startswith("/api/docs") or path.startswith("/api/triggers/webhook/"):
        return None

    # Setup redirect — if no users, only allow setup endpoints
    if needs_setup():
        if path not in PUBLIC_PATHS:
            return jsonify({"error": "Setup required", "needs_setup": True}), 403

    # Require auth for all other API paths
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401

# --------------- Register blueprints ---------------
from routes.overview import bp as overview_bp
from routes.reports import bp as reports_bp
from routes.agents import bp as agents_bp
from routes.routines import bp as routines_bp
from routes.skills import bp as skills_bp
from routes.templates_routes import bp as templates_bp
from routes.memory import bp as memory_bp
from routes.costs import bp as costs_bp
from routes.config import bp as config_bp
from routes.files import bp as files_bp
from routes.integrations import bp as integrations_bp
from routes.scheduler import bp as scheduler_bp
from routes.services import bp as services_bp
from routes.auth_routes import bp as auth_bp
from routes.systems import bp as systems_bp
from routes.docs import bp as docs_bp
from routes.mempalace import bp as mempalace_bp
from routes.tasks import bp as tasks_bp
from routes.triggers import bp as triggers_bp
from routes.backups import bp as backups_bp
from routes.providers import bp as providers_bp

app.register_blueprint(overview_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(routines_bp)
app.register_blueprint(skills_bp)
app.register_blueprint(templates_bp)
app.register_blueprint(memory_bp)
app.register_blueprint(costs_bp)
app.register_blueprint(config_bp)
app.register_blueprint(files_bp)
app.register_blueprint(integrations_bp)
app.register_blueprint(scheduler_bp)
app.register_blueprint(services_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(systems_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(mempalace_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(triggers_bp)
app.register_blueprint(backups_bp)
app.register_blueprint(providers_bp)

# --------------- Social Auth blueprints ---------------
from auth.youtube import bp as youtube_auth_bp
from auth.instagram import bp as instagram_auth_bp
from auth.linkedin import bp as linkedin_auth_bp
from auth.twitter import bp as twitter_auth_bp
from auth.tiktok import bp as tiktok_auth_bp
from auth.twitch import bp as twitch_auth_bp

app.register_blueprint(youtube_auth_bp)
app.register_blueprint(instagram_auth_bp)
app.register_blueprint(linkedin_auth_bp)
app.register_blueprint(twitter_auth_bp)
app.register_blueprint(tiktok_auth_bp)
app.register_blueprint(twitch_auth_bp)

def _get_local_version():
    """Read current version from pyproject.toml."""
    try:
        pyproject = WORKSPACE / "pyproject.toml"
        for line in pyproject.read_text().splitlines():
            if line.startswith("version"):
                return line.split('"')[1]
    except Exception:
        pass
    return "unknown"


@app.route("/api/version")
def api_version():
    """Return current version from pyproject.toml."""
    return {"version": _get_local_version()}


@app.route("/api/agents/active")
def api_agents_active():
    """Return currently active agents from hook-generated status file."""
    import json
    status_file = WORKSPACE / ".claude" / "agent-status.json"
    try:
        if status_file.is_file():
            data = json.loads(status_file.read_text())
            # Filter entries older than 10 minutes (stale)
            from datetime import datetime, timezone, timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
            active = []
            for entry in data.get("active_agents", []):
                try:
                    started = datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00"))
                    if started > cutoff:
                        active.append(entry)
                except (KeyError, ValueError):
                    pass
            return {"active_agents": active, "last_updated": data.get("last_updated")}
    except Exception:
        pass
    return {"active_agents": [], "last_updated": None}


# --- Version check with 1h cache ---
_version_cache = {"data": None, "expires": 0}

@app.route("/api/version/check")
def api_version_check():
    """Compare local version against latest GitHub release (cached 1h)."""
    import time
    import requests as http_requests

    now = time.time()
    if _version_cache["data"] and now < _version_cache["expires"]:
        return _version_cache["data"]

    current = _get_local_version()
    result = {
        "current": current,
        "latest": None,
        "update_available": False,
        "release_url": None,
        "release_notes": None,
    }

    try:
        resp = http_requests.get(
            "https://api.github.com/repos/EvolutionAPI/evo-nexus/releases/latest",
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            result["latest"] = latest
            result["release_url"] = data.get("html_url")
            result["release_notes"] = data.get("body", "")[:500]

            # Compare versions (semver-like: major.minor.patch)
            def parse_ver(v):
                try:
                    return tuple(int(x) for x in v.split("."))
                except (ValueError, AttributeError):
                    return (0, 0, 0)

            if parse_ver(latest) > parse_ver(current):
                result["update_available"] = True
    except Exception:
        pass

    _version_cache["data"] = result
    _version_cache["expires"] = now + 3600  # 1 hour
    return result

@app.route("/api/social-accounts")
def social_accounts():
    from env_manager import all_platforms_with_accounts
    return {"platforms": all_platforms_with_accounts()}

@app.route("/api/social-accounts/<platform>/<int:index>", methods=["DELETE"])
def delete_social_account(platform, index):
    from env_manager import delete_account, all_platforms_with_accounts
    delete_account(platform, index)
    return {"ok": True, "platforms": all_platforms_with_accounts()}

# --------------- Serve React build ---------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    full = FRONTEND_DIST / path
    if full.is_file():
        return send_from_directory(str(FRONTEND_DIST), path)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return send_from_directory(str(FRONTEND_DIST), "index.html")
    return {"error": "Frontend not built. Run npm build in frontend/"}, 404


if __name__ == "__main__":
    # Read port from workspace.yaml or env, fallback to 8080
    port = int(os.environ.get("EVONEXUS_PORT", 8080))
    try:
        import yaml
        config_path = WORKSPACE / "config" / "workspace.yaml"
        if config_path.is_file():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            if cfg and cfg.get("port"):
                port = int(cfg["port"])
    except Exception:
        pass
    # Start scheduler in background thread
    import threading
    def _run_pending_tasks():
        """Check for pending scheduled tasks and execute them."""
        from datetime import datetime as _dt, timezone as _tz
        from models import ScheduledTask
        from routes.tasks import _execute_task

        try:
            now = _dt.now(_tz.utc)
            pending = ScheduledTask.query.filter(
                ScheduledTask.status == "pending",
                ScheduledTask.scheduled_at <= now,
            ).all()

            for task in pending:
                log_path = WORKSPACE / "ADWs" / "logs" / "scheduler.log"
                with open(log_path, "a") as log:
                    log.write(f"  [{_dt.now().strftime('%H:%M')}] Running scheduled task #{task.id}: {task.name}\n")

                t = threading.Thread(target=_execute_task_with_context, args=(task.id,), daemon=True)
                t.start()
        except Exception as e:
            pass  # Don't crash scheduler loop on task errors

    def _execute_task_with_context(task_id):
        with app.app_context():
            from routes.tasks import _execute_task
            _execute_task(task_id)

    def _run_scheduler():
        log_path = WORKSPACE / "ADWs" / "logs" / "scheduler.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("scheduler", WORKSPACE / "scheduler.py")
            sched_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sched_module)
            sched_module.setup_schedule()

            import schedule as sched_lib
            import time as _time
            from datetime import datetime as _dt

            with open(log_path, "a") as log:
                log.write(f"\n[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] Scheduler started ({len(sched_lib.get_jobs())} routines)\n")
                log.flush()

                while True:
                    sched_lib.run_pending()
                    # Check for one-off scheduled tasks
                    with app.app_context():
                        _run_pending_tasks()
                    _time.sleep(30)
        except Exception as e:
            with open(log_path, "a") as log:
                log.write(f"Scheduler error: {e}\n")
            print(f"Scheduler failed to start: {e}")

    sched_thread = threading.Thread(target=_run_scheduler, daemon=True, name="scheduler")
    sched_thread.start()
    print(f"  Scheduler started in background")

    app.run(host="0.0.0.0", port=port, debug=False)
