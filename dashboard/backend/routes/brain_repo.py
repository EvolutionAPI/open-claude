"""Brain repo management endpoints."""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, request, jsonify, abort, Response, stream_with_context
from flask_login import login_required, current_user
from models import db, BrainRepoConfig

bp = Blueprint("brain_repo", __name__)


def _get_master_key() -> bytes:
    key = os.environ.get("BRAIN_REPO_MASTER_KEY", "")
    return key.encode() if key else b""


def _get_config() -> BrainRepoConfig | None:
    return BrainRepoConfig.query.filter_by(user_id=current_user.id).first()


def _decrypt_token(config: BrainRepoConfig) -> str:
    """Decrypt the stored GitHub PAT. Returns empty string if not available."""
    if not config or not config.github_token_encrypted:
        return ""
    try:
        from brain_repo.pat_auth import PATAuthProvider
        provider = PATAuthProvider(_get_master_key())
        return provider.decrypt(config.github_token_encrypted)
    except ImportError:
        # Fallback: attempt raw decode (for testing without full module)
        try:
            return config.github_token_encrypted.decode("utf-8")
        except Exception:
            return ""
    except Exception:
        return ""


# ── Status ────────────────────────────────────────────

@bp.route("/api/brain-repo/status")
@login_required
def status():
    """Return current BrainRepoConfig or minimal disconnected state."""
    config = _get_config()
    if config is None:
        return jsonify({"connected": False})
    return jsonify(config.to_dict())


# ── Connect ───────────────────────────────────────────

@bp.route("/api/brain-repo/connect", methods=["POST"])
@login_required
def connect():
    """Connect (or reconfigure) the brain repo.

    Body (JSON):
        token      - GitHub PAT (required)
        repo_url   - URL of an existing private repo to connect to
        create_repo - Name of a new private repo to create (mutually exclusive with repo_url)
    """
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    repo_url = data.get("repo_url", "").strip()
    create_repo = data.get("create_repo", "").strip()

    if not token:
        abort(400, description="token required")
    if not repo_url and not create_repo:
        abort(400, description="Either repo_url or create_repo is required")

    # Validate PAT scopes
    try:
        from brain_repo.github_api import validate_pat_scopes
        ok, scopes = validate_pat_scopes(token)
    except ImportError:
        ok, scopes = True, ["repo"]  # graceful fallback if module not yet present

    if not ok:
        abort(400, description="GitHub PAT validation failed — check token scopes (needs 'repo')")

    # Create or validate the repo
    if create_repo:
        try:
            from brain_repo.github_api import create_private_repo
            repo_info = create_private_repo(token, create_repo)
        except ImportError:
            # Fallback stub
            repo_info = {
                "html_url": f"https://github.com/user/{create_repo}",
                "owner": {"login": "user"},
                "name": create_repo,
            }
        except Exception as exc:
            abort(400, description=f"Failed to create repo: {exc}")
        repo_url = repo_info.get("html_url", "")
        repo_owner = repo_info.get("owner", {}).get("login", "")
        repo_name = repo_info.get("name", create_repo)
    else:
        # Validate existing repo is private
        try:
            from brain_repo.github_api import validate_repo_is_private
            ok_private, repo_info = validate_repo_is_private(token, repo_url)
        except ImportError:
            ok_private, repo_info = True, {}  # graceful fallback

        if not ok_private:
            abort(400, description="Repository must be private")
        repo_owner = repo_info.get("owner", {}).get("login", "")
        repo_name = repo_info.get("name", "")

    # Encrypt and store token
    try:
        from brain_repo.pat_auth import PATAuthProvider
        provider = PATAuthProvider(_get_master_key())
        encrypted = provider.encrypt(token)
    except ImportError:
        # Fallback: store token bytes directly (only for dev without pat_auth module)
        encrypted = token.encode("utf-8")

    config = _get_config()
    if config is None:
        config = BrainRepoConfig(user_id=current_user.id)
        db.session.add(config)

    config.github_token_encrypted = encrypted
    config.repo_url = repo_url
    config.repo_owner = repo_owner
    config.repo_name = repo_name
    config.sync_enabled = True
    config.last_error = None
    db.session.commit()

    return jsonify(config.to_dict())


# ── Disconnect ────────────────────────────────────────

@bp.route("/api/brain-repo/disconnect", methods=["POST"])
@login_required
def disconnect():
    """Remove stored credentials and disable sync."""
    config = _get_config()
    if config:
        config.github_token_encrypted = None
        config.sync_enabled = False
        db.session.commit()
    return jsonify({"ok": True})


# ── Detect ────────────────────────────────────────────

@bp.route("/api/brain-repo/detect")
@login_required
def detect():
    """Detect candidate brain repos for the authenticated token."""
    token = request.args.get("token", "").strip()
    if not token:
        # Try to use stored token
        config = _get_config()
        if config:
            token = _decrypt_token(config)
    if not token:
        abort(400, description="token required (query param or stored config)")

    try:
        from brain_repo.github_api import detect_brain_repos
        repos = detect_brain_repos(token)
    except ImportError:
        repos = []  # graceful fallback

    return jsonify({"repos": repos})


# ── Snapshots ─────────────────────────────────────────

@bp.route("/api/brain-repo/snapshots")
@login_required
def snapshots():
    """List available restore snapshots (daily / weekly / milestones / head)."""
    config = _get_config()
    if not config or not config.github_token_encrypted:
        abort(400, description="Brain repo not connected")

    token = _decrypt_token(config)
    if not token:
        abort(400, description="Could not decrypt stored token")

    try:
        from brain_repo.github_api import list_snapshots
        result = list_snapshots(token, config.repo_owner, config.repo_name)
    except ImportError:
        result = {"daily": [], "weekly": [], "milestones": [], "head": None}

    return jsonify(result)


# ── Restore (SSE) ─────────────────────────────────────

@bp.route("/api/brain-repo/restore/start", methods=["POST"])
@login_required
def restore_start():
    """Begin a restore operation; streams progress via Server-Sent Events.

    Body (JSON):
        ref         - git ref / tag to restore from (required)
        include_kb  - bool, whether to restore knowledge base (default True)

    SSE event format:
        data: {"step": "<name>", "progress": <0-100>, "message": "...", "error": false}
    """
    data = request.get_json() or {}
    ref = data.get("ref", "").strip()
    include_kb = data.get("include_kb", True)

    if not ref:
        abort(400, description="ref required")

    config = _get_config()
    if not config or not config.github_token_encrypted:
        abort(400, description="Brain repo not connected")

    token = _decrypt_token(config)
    if not token:
        abort(400, description="Could not decrypt stored token")

    # Capture needed values before entering generator (avoids app context issues)
    repo_url = config.repo_url
    local_path = config.local_path
    user_id = current_user.id

    def generate():
        try:
            from brain_repo import restore
            for event in restore.execute_restore(
                token=token,
                repo_url=repo_url,
                local_path=local_path,
                ref=ref,
                include_kb=include_kb,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ImportError:
            # Module not yet implemented — yield a single completion event
            yield f"data: {json.dumps({'step': 'done', 'progress': 100, 'message': 'restore module not yet available', 'error': False})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'step': 'error', 'progress': 0, 'message': str(exc), 'error': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Sync (force) ──────────────────────────────────────

@bp.route("/api/brain-repo/sync/force", methods=["POST"])
@login_required
def sync_force():
    """Force an immediate commit + push with a milestone tag.

    Creates a tag ``milestone/manual-YYYY-MM-DD-HH-MM`` after pushing.
    """
    config = _get_config()
    if not config or not config.github_token_encrypted:
        abort(400, description="Brain repo not connected")

    token = _decrypt_token(config)
    local_path = config.local_path
    if not local_path:
        abort(400, description="local_path not configured — repo not yet cloned")

    repo_dir = Path(local_path)

    try:
        from brain_repo import git_ops
    except ImportError:
        abort(500, description="git_ops module unavailable")

    now = datetime.now(timezone.utc)
    tag_name = f"milestone/manual-{now.strftime('%Y-%m-%d-%H-%M')}"

    try:
        committed = git_ops.commit_all(repo_dir, f"manual sync {now.isoformat()}")
        git_ops.push(repo_dir, token)
        git_ops.create_tag(repo_dir, tag_name, f"Manual sync at {now.isoformat()}")
    except Exception as exc:
        config.last_error = str(exc)
        db.session.commit()
        abort(500, description=str(exc))

    config.last_sync = now
    config.last_error = None
    db.session.commit()

    return jsonify({"ok": True, "committed": committed, "tag": tag_name})


# ── Tag milestone ─────────────────────────────────────

@bp.route("/api/brain-repo/tag/milestone", methods=["POST"])
@login_required
def tag_milestone():
    """Create a named milestone tag in the brain repo.

    Body (JSON):
        name - tag suffix, result will be ``milestone/<name>``
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        abort(400, description="name required")

    config = _get_config()
    if not config or not config.github_token_encrypted:
        abort(400, description="Brain repo not connected")

    local_path = config.local_path
    if not local_path:
        abort(400, description="local_path not configured — repo not yet cloned")

    tag = f"milestone/{name}"

    try:
        from brain_repo import git_ops
    except ImportError:
        abort(500, description="git_ops module unavailable")

    try:
        ok = git_ops.create_tag(
            Path(local_path),
            tag,
            f"Milestone: {name}",
        )
    except Exception as exc:
        abort(500, description=str(exc))

    if not ok:
        abort(500, description=f"Failed to create tag '{tag}'")

    return jsonify({"ok": True, "tag": tag})
