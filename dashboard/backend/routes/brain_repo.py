"""Brain repo management endpoints."""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, request, jsonify, abort, Response, stream_with_context
from flask_login import login_required, current_user
from werkzeug.exceptions import HTTPException
from models import db, BrainRepoConfig

log = logging.getLogger(__name__)

bp = Blueprint("brain_repo", __name__)


@bp.errorhandler(HTTPException)
def _http_exception_to_json(exc: HTTPException):
    """Convert all abort() calls inside this blueprint into JSON responses.

    Flask's default for ``abort(400, description="...")`` is HTML — the description
    is buried inside an HTML body that the SPA can't usefully parse. Returning
    JSON lets ``lib/api.ts`` surface ``data.error`` to the user verbatim
    (e.g. "Failed to create repo: name already exists on this account").
    """
    return jsonify({"error": exc.description, "code": exc.code}), exc.code or 500


def _get_master_key() -> bytes | None:
    """Return the Fernet master key from env, or None if missing/empty.

    Callers must handle a None return gracefully — ``Fernet(b"")`` would
    crash, so we surface the absence explicitly instead. ``app.py`` is
    supposed to auto-generate ``BRAIN_REPO_MASTER_KEY`` at startup, so a
    None here means that bootstrap did not run (e.g. tests, bare imports).
    """
    key = os.environ.get("BRAIN_REPO_MASTER_KEY", "")
    if not key:
        return None
    return key.encode()


def _get_config() -> BrainRepoConfig | None:
    return BrainRepoConfig.query.filter_by(user_id=current_user.id).first()


def _initialize_remote_brain_repo(
    token: str,
    repo_url: str,
    repo_name: str,
    owner_username: str,
    github_username: str,
) -> str | None:
    """Bootstrap a freshly-created (empty) GitHub repo with the brain-repo skeleton.

    Steps:
        1. Create a local working copy under
           ``<WORKSPACE>/dashboard/data/brain-repos/<repo_name>``
        2. ``git init`` + ``remote add origin`` (token-embedded URL)
        3. Call ``manifest.initialize_brain_repo`` to drop in the directory
           structure, ``.evo-brain`` marker, ``manifest.yaml``, README, and
           ``.gitignore``
        4. Configure git author (commits show as the GitHub user)
        5. Commit everything and push to ``origin/main``

    Returns the local path on success, or None on failure (callers should not
    abort the connect — the GitHub repo exists, only the bootstrap commit is
    missing, and a future sync will repopulate it).
    """
    import subprocess

    workspace = Path(__file__).resolve().parent.parent.parent.parent
    base_dir = workspace / "dashboard" / "data" / "brain-repos"
    base_dir.mkdir(parents=True, exist_ok=True)
    local_path = base_dir / repo_name

    # Wipe stale clone if present (re-connect after a disconnect)
    if local_path.exists():
        import shutil
        shutil.rmtree(local_path, ignore_errors=True)

    try:
        from brain_repo import git_ops, manifest
    except ImportError as exc:
        log.warning("brain_repo helpers unavailable, skipping bootstrap: %s", exc)
        return None

    try:
        local_path.mkdir(parents=True, exist_ok=True)

        # We use ``git init`` + ``remote add`` rather than ``git clone`` because
        # the remote is empty and ``clone`` of an empty repo emits warnings and
        # leaves an unhelpful state.
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=local_path, check=True, capture_output=True, timeout=30,
        )
        # Token-embedded auth URL — never logged
        if "://" in repo_url:
            scheme, rest = repo_url.split("://", 1)
            auth_url = f"{scheme}://{token}@{rest}"
        else:
            auth_url = repo_url
        subprocess.run(
            ["git", "remote", "add", "origin", auth_url],
            cwd=local_path, check=True, capture_output=True, timeout=30,
        )

        # Drop in the brain-repo skeleton (.evo-brain marker, manifest.yaml, dirs)
        manifest.initialize_brain_repo(local_path, {
            "workspace_name": owner_username or "",
            "owner_username": owner_username or "",
            "github_username": github_username or "",
        })

        # Commit author — use the GitHub username so the commit attributes correctly
        author_name = github_username or owner_username or "EvoNexus"
        author_email = (
            f"{github_username}@users.noreply.github.com"
            if github_username else "evonexus@users.noreply.github.com"
        )
        subprocess.run(
            ["git", "config", "user.name", author_name],
            cwd=local_path, check=True, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "config", "user.email", author_email],
            cwd=local_path, check=True, capture_output=True, timeout=10,
        )

        committed = git_ops.commit_all(local_path, "feat(brain-repo): initial structure")
        if committed:
            pushed = git_ops.push(local_path, token)
            if not pushed:
                log.warning("brain repo initial push failed for %s", repo_name)
        return str(local_path)
    except Exception as exc:
        log.warning("Failed to bootstrap brain repo %s: %s", repo_name, exc)
        return None


def _decrypt_token(config: BrainRepoConfig) -> str:
    """Decrypt the stored GitHub PAT. Returns empty string if not available."""
    if not config or not config.github_token_encrypted:
        return ""
    master_key = _get_master_key()
    if master_key is None:
        # No master key available — fall back to treating the stored blob as
        # raw token bytes (matches the encrypt-side fallback below).
        log.warning("BRAIN_REPO_MASTER_KEY missing; decrypting as raw bytes")
        try:
            return config.github_token_encrypted.decode("utf-8")
        except Exception:
            return ""
    try:
        from brain_repo.github_oauth import decrypt_token
        return decrypt_token(config.github_token_encrypted, master_key)
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


# ── Validate token ────────────────────────────────────

@bp.route("/api/brain-repo/validate-token", methods=["POST"])
@login_required
def validate_token():
    """Validate a GitHub PAT without persisting anything.

    Body (JSON):
        token - GitHub PAT (required)

    Returns on success:
        {"ok": true, "scopes": [...], "username": "..."}
    On invalid token:
        400 {"ok": false, "error": "..."}
    """
    data = request.get_json() or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    try:
        from brain_repo.github_api import validate_pat_scopes, get_github_username
    except ImportError:
        # Graceful fallback — module unavailable in this environment
        return jsonify({"ok": False, "error": "brain_repo.github_api unavailable"}), 400

    try:
        ok, scopes = validate_pat_scopes(token)
    except Exception as exc:
        log.warning("validate_pat_scopes failed: %s", exc)
        return jsonify({"ok": False, "error": f"validation failed: {exc}"}), 400

    if not ok:
        return jsonify({
            "ok": False,
            "error": "GitHub PAT validation failed — check token and ensure 'repo' scope is granted",
            "scopes": scopes,
        }), 400

    try:
        username = get_github_username(token)
    except Exception as exc:
        log.warning("get_github_username failed: %s", exc)
        username = ""

    return jsonify({"ok": True, "scopes": scopes, "username": username})


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
    bootstrap_local_path: str | None = None
    if create_repo:
        try:
            from brain_repo.github_api import create_private_repo, get_github_username
            repo_info = create_private_repo(token, create_repo)
        except ImportError:
            # Fallback stub
            repo_info = {
                "html_url": f"https://github.com/user/{create_repo}",
                "owner": {"login": "user"},
                "name": create_repo,
            }
        except Exception as exc:
            # Friendlier message for the common case (repo already exists → 422)
            err_str = str(exc)
            if "422" in err_str or "already exists" in err_str.lower():
                abort(400, description=(
                    f"O repositório '{create_repo}' já existe na sua conta. "
                    "Use a opção 'Usar existente' para conectá-lo, "
                    "ou escolha um nome diferente."
                ))
            abort(400, description=f"Falha ao criar repo: {exc}")
        repo_url = repo_info.get("html_url", "")
        repo_owner = repo_info.get("owner", {}).get("login", "")
        repo_name = repo_info.get("name", create_repo)

        # Bootstrap the empty remote: clone-init + initialize_brain_repo + commit + push.
        # Without this, the repo has no .evo-brain marker so detect_brain_repos
        # (GitHub code search) cannot find it later, and Use-existing rejects it
        # as "incompatible".
        try:
            github_username = get_github_username(token)
        except Exception:
            github_username = repo_owner
        bootstrap_local_path = _initialize_remote_brain_repo(
            token=token,
            repo_url=repo_url,
            repo_name=repo_name,
            owner_username=current_user.username or repo_owner,
            github_username=github_username,
        )
    else:
        # Validate existing repo is private
        try:
            from brain_repo.github_api import get_repo_info
            ok_private, repo_info = get_repo_info(token, repo_url)
        except ImportError:
            ok_private, repo_info = True, {}  # graceful fallback

        if not ok_private:
            abort(400, description="Repository must be private")
        repo_owner = repo_info.get("owner", {}).get("login", "")
        repo_name = repo_info.get("name", "")

    # Encrypt and store token
    master_key = _get_master_key()
    if master_key is None:
        # No master key configured — fall back to storing raw bytes and warn.
        # The decrypt side mirrors this behaviour.
        log.warning("BRAIN_REPO_MASTER_KEY missing; storing token as raw bytes")
        encrypted = token.encode("utf-8")
    else:
        try:
            from brain_repo.github_oauth import PATAuthProvider
            provider = PATAuthProvider(token, master_key)
            encrypted = provider.encrypt_token()
        except ImportError:
            # Fallback: store token bytes directly (only for dev without module)
            encrypted = token.encode("utf-8")

    config = _get_config()
    if config is None:
        config = BrainRepoConfig(user_id=current_user.id)
        db.session.add(config)

    config.github_token_encrypted = encrypted
    config.repo_url = repo_url
    config.repo_owner = repo_owner
    config.repo_name = repo_name
    if bootstrap_local_path:
        config.local_path = bootstrap_local_path
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
