"""Workspace file manager — CRUD for workspace/ and admin-scoped roots."""

import mimetypes
import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, abort, send_file, current_app
from flask_login import login_required, current_user

from models import has_permission, has_workspace_folder_access
from routes.auth_routes import require_permission

bp = Blueprint("workspace", __name__)

# ── Constants ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_DIR = REPO_ROOT / "workspace"
ADMIN_ROOTS = [REPO_ROOT / ".claude", REPO_ROOT / "config", REPO_ROOT / "docs"]
BLOCKLIST_PREFIXES = (
    ".git", "node_modules", "dist", ".venv", "__pycache__",
    "backups", ".mypy_cache", ".pytest_cache", "target", "build",
    ".next", ".turbo", "coverage",
)
TRASH_DIR = WORKSPACE_DIR / ".trash"
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
MAX_CONTENT_SIZE = 2 * 1024 * 1024  # 2MB



# ── Helpers ────────────────────────────────────────────────────────────────

def _allowed_roots_for(user, require_admin: bool) -> list[Path]:
    """Return the list of allowed root paths for the given user."""
    if not require_admin:
        return [WORKSPACE_DIR]
    if has_permission(user.role, "config", "manage"):
        return [WORKSPACE_DIR] + ADMIN_ROOTS
    _audit("denied", "", result="denied", reason="no_permission")
    abort(403, description="Admin access requires config:manage permission")


def _resolve_safe(path: str, *, require_admin: bool = False) -> Path:
    """Resolve a repo-root-relative path and enforce security invariants.

    Raises abort(403) on any security violation.
    """
    path_str = str(path) if path else ""

    # 1. Reject empty, absolute, or NUL-containing paths
    if not path or "\x00" in path:
        _audit("denied", path_str, result="denied", reason="invalid_path")
        abort(403, description="Invalid path")
    if Path(path).is_absolute():
        _audit("denied", path_str, result="denied", reason="invalid_path")
        abort(403, description="Absolute paths not allowed")

    # 2. Resolve to absolute path
    full = (REPO_ROOT / path).resolve()

    # 3. Must be inside REPO_ROOT
    try:
        rel = full.relative_to(REPO_ROOT.resolve())
    except ValueError:
        _audit("denied", path_str, result="denied", reason="path_traversal")
        abort(403, description="Path traversal detected")

    # 4. Blocklist check: no segment may start with a blocklisted prefix
    for part in rel.parts:
        for prefix in BLOCKLIST_PREFIXES:
            if part == prefix or part.startswith(prefix + "/"):
                _audit("denied", path_str, result="denied", reason="blocklist")
                abort(403, description=f"Access to '{part}' is blocked")

    # 5. Check allowed roots
    allowed_roots = _allowed_roots_for(current_user, require_admin)
    if not any(
        full == r.resolve() or _is_relative_to(full, r.resolve())
        for r in allowed_roots
    ):
        if not require_admin and any(
            full == r.resolve() or _is_relative_to(full, r.resolve())
            for r in ADMIN_ROOTS
        ):
            _audit("denied", path_str, result="denied", reason="no_permission")
            abort(403, description="Admin path requires elevated permission")
        _audit("denied", path_str, result="denied", reason="out_of_scope")
        abort(403, description="Path outside allowed roots")

    return full


def _is_relative_to(path: Path, base: Path) -> bool:
    """Python 3.8-compatible relative_to check."""
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _audit(op: str, path: str, *, result: str = "ok", **extra):
    """Record a workspace mutation — delegates to workspace_audit.audit_mutation.

    Fail-safe: errors never propagate.
    """
    try:
        try:
            user_id = current_user.id if current_user.is_authenticated else None
            role = current_user.role if current_user.is_authenticated else "anonymous"
        except Exception:
            user_id, role = None, "anonymous"

        from workspace_audit import audit_mutation
        audit_mutation(
            user_id=user_id,
            role=role,
            op=op,
            path=path.replace("\\", "/"),
            result=result,
            extra=extra if extra else None,
        )
    except Exception as exc:
        try:
            current_app.logger.error(f"[workspace audit] failed to write: {exc}")
        except Exception:
            pass


def _repo_rel(full: Path) -> str:
    """Return the repo-root-relative path as a forward-slash string."""
    try:
        return str(full.relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(full).replace("\\", "/")


def _stat_entry(entry: Path, base: Path) -> dict | None:
    """Build a tree entry dict for a file or directory. Returns None on broken symlinks."""
    try:
        stat = entry.stat()
    except (FileNotFoundError, OSError):
        return None  # broken symlink or permission issue
    try:
        is_dir = entry.is_dir()
    except (FileNotFoundError, OSError):
        return None
    mime, _ = mimetypes.guess_type(entry.name)
    item = {
        "name": entry.name,
        "path": _repo_rel(entry),
        "type": "dir" if is_dir else "file",
        "is_dir": is_dir,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "modified": stat.st_mtime,
        "extension": entry.suffix.lower() if not is_dir else None,
    }
    if not is_dir and mime:
        item["mime"] = mime
    return item


def _is_blocklisted(name: str) -> bool:
    for prefix in BLOCKLIST_PREFIXES:
        if name == prefix or name.startswith(prefix):
            return True
    return False


def _check_folder_access(path_str: str):
    """Abort 403 if user's role cannot access this workspace folder.

    Only enforced for paths inside WORKSPACE_DIR. Admin paths are skipped
    (they are gated by config:manage permission already).
    """
    if not current_user.is_authenticated:
        return
    # Only enforce for workspace/ paths
    parts = path_str.strip("/").split("/")
    if not parts or parts[0] != "workspace":
        return
    if not has_workspace_folder_access(current_user.role, path_str):
        _audit("denied", path_str, result="denied", reason="folder_restricted")
        abort(403, description="Access to this workspace folder is restricted")


# ── Endpoints ──────────────────────────────────────────────────────────────

@bp.route("/api/workspace/tree")
@login_required
@require_permission("workspace", "view")
def workspace_tree():
    """List directory contents with optional depth."""
    path = request.args.get("path", "workspace")
    depth = request.args.get("depth", 1, type=int)
    if depth < 1:
        depth = 1

    # Decide if admin paths are needed
    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    ) if path else False

    full = _resolve_safe(path, require_admin=require_admin)

    if not full.exists():
        return jsonify({"error": "Directory not found", "code": "not_found"}), 404
    if not full.is_dir():
        return jsonify({"error": "Path is not a directory", "code": "bad_path"}), 400

    def _safe_is_dir(p: Path) -> bool:
        try:
            return p.is_dir()
        except OSError:
            return False

    def _build_entries(directory: Path, current_depth: int) -> list:
        entries = []
        try:
            children = sorted(directory.iterdir(), key=lambda e: (not _safe_is_dir(e), e.name.lower()))
        except (PermissionError, OSError):
            return entries

        for entry in children:
            if _is_blocklisted(entry.name):
                continue
            item = _stat_entry(entry, full)
            if item is None:
                continue  # broken symlink / inaccessible
            if item["is_dir"] and current_depth > 1:
                item["children"] = _build_entries(entry, current_depth - 1)
            entries.append(item)
        return entries

    entries = _build_entries(full, depth)

    # Filter top-level workspace folders based on role access
    rel_check = _repo_rel(full)
    if rel_check == "workspace" and current_user.is_authenticated:
        entries = [
            e for e in entries
            if not e.get("is_dir") or has_workspace_folder_access(
                current_user.role, f"workspace/{e['name']}"
            )
        ]

    # Build breadcrumbs from repo-rel path
    rel = _repo_rel(full)
    parts = [p for p in rel.split("/") if p]
    breadcrumbs = []
    acc = ""
    for part in parts:
        acc = f"{acc}/{part}" if acc else part
        breadcrumbs.append({"name": part, "path": acc})

    return jsonify({
        "path": rel,
        "entries": entries,
        "items": entries,  # alias for frontend compatibility
        "breadcrumbs": breadcrumbs,
    })


@bp.route("/api/workspace/file")
@login_required
@require_permission("workspace", "view")
def workspace_file_read():
    """Read file content."""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if not full.exists():
        return jsonify({"error": "File not found", "code": "not_found"}), 404
    if full.is_dir():
        return jsonify({"error": "Path is a directory", "code": "bad_path"}), 400

    stat = full.stat()
    size = stat.st_size
    mtime = stat.st_mtime
    mime, _ = mimetypes.guess_type(full.name)
    mime = mime or "application/octet-stream"
    rel = _repo_rel(full)

    # Audit only for admin paths
    is_admin_path = not _is_relative_to(full, WORKSPACE_DIR.resolve())

    if size > MAX_CONTENT_SIZE:
        if is_admin_path:
            _audit("read", rel, size=size, mime=mime)
        return jsonify({"path": rel, "mime": mime, "size": size, "mtime": mtime, "truncated": True})

    try:
        content = full.read_text("utf-8")
        if is_admin_path:
            _audit("read", rel, size=size, mime=mime)
        return jsonify({"path": rel, "content": content, "encoding": "utf-8", "mime": mime, "size": size, "mtime": mtime})
    except UnicodeDecodeError:
        if is_admin_path:
            _audit("read", rel, size=size, mime=mime)
        return jsonify({"path": rel, "binary": True, "mime": mime, "size": size, "mtime": mtime})


@bp.route("/api/workspace/file", methods=["PUT"])
@login_required
@require_permission("workspace", "manage")
def workspace_file_write():
    """Write file content atomically."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    content = data.get("content", "")

    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if full.is_dir():
        return jsonify({"error": "Path is a directory", "code": "bad_path"}), 409

    if not full.parent.exists():
        return jsonify({"error": "Parent directory not found", "code": "not_found"}), 404

    tmp = full.parent / f"{full.name}.tmp-{uuid.uuid4().hex}"
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(full))
    except OSError as e:
        tmp.unlink(missing_ok=True)
        _audit("write", _repo_rel(full), result="error", reason=str(e))
        return jsonify({"error": str(e), "code": "io_error"}), 500

    stat = full.stat()
    rel = _repo_rel(full)
    _audit("write", rel, bytes=len(content.encode("utf-8")), size=stat.st_size)
    return jsonify({"path": rel, "size": stat.st_size, "mtime": stat.st_mtime})


@bp.route("/api/workspace/file", methods=["POST"])
@login_required
@require_permission("workspace", "manage")
def workspace_file_create():
    """Create an empty file."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")

    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if full.exists():
        return jsonify({"error": "File already exists", "code": "conflict"}), 409

    if not full.parent.exists():
        return jsonify({"error": "Parent directory not found", "code": "not_found"}), 404

    try:
        full.touch()
    except OSError as e:
        _audit("create", _repo_rel(full), result="error", reason=str(e))
        return jsonify({"error": str(e), "code": "io_error"}), 500

    stat = full.stat()
    rel = _repo_rel(full)
    _audit("create", rel, size=0)
    return jsonify({"path": rel, "size": 0, "mtime": stat.st_mtime}), 201


@bp.route("/api/workspace/folder", methods=["POST"])
@login_required
@require_permission("workspace", "manage")
def workspace_folder_create():
    """Create a directory."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")

    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if full.exists():
        return jsonify({"error": "Directory already exists", "code": "conflict"}), 409

    try:
        full.mkdir(parents=True)
    except OSError as e:
        _audit("create_folder", _repo_rel(full), result="error", reason=str(e))
        return jsonify({"error": str(e), "code": "io_error"}), 500

    stat = full.stat()
    rel = _repo_rel(full)
    _audit("create_folder", rel)
    return jsonify({"path": rel, "type": "dir", "mtime": stat.st_mtime}), 201


@bp.route("/api/workspace/rename", methods=["POST"])
@login_required
@require_permission("workspace", "manage")
def workspace_rename():
    """Rename a file or directory (same directory only in v1)."""
    data = request.get_json(silent=True) or {}
    from_path = data.get("from", "")
    to_path = data.get("to", "")

    if not from_path or not to_path:
        return jsonify({"error": "from and to are required", "code": "bad_path"}), 400

    # v1: same directory only
    if Path(from_path).parent != Path(to_path).parent:
        return jsonify({"error": "move between folders not supported in v1", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / from_path).resolve(), WORKSPACE_DIR.resolve()
    )
    full_from = _resolve_safe(from_path, require_admin=require_admin)
    full_to = _resolve_safe(to_path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full_from))
    _check_folder_access(_repo_rel(full_to))

    if not full_from.exists():
        return jsonify({"error": "Source not found", "code": "not_found"}), 404

    if full_to.exists():
        return jsonify({"error": "Destination already exists", "code": "conflict"}), 409

    try:
        full_from.rename(full_to)
    except OSError as e:
        _audit("rename", _repo_rel(full_from), result="error", reason=str(e), **{"to": _repo_rel(full_to)})
        return jsonify({"error": str(e), "code": "io_error"}), 500

    stat = full_to.stat()
    from_rel = _repo_rel(full_from)
    to_rel = _repo_rel(full_to)
    _audit("rename", from_rel, **{"to": to_rel, "size": stat.st_size})
    return jsonify({"from": from_rel, "to": to_rel, "size": stat.st_size, "mtime": stat.st_mtime})


@bp.route("/api/workspace/file", methods=["DELETE"])
@login_required
@require_permission("workspace", "manage")
def workspace_file_delete():
    """Soft delete: move to TRASH_DIR/YYYY-MM-DD/<original_repo_relative_path>."""
    path = request.args.get("path", "")

    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if not full.exists():
        return jsonify({"error": "File not found", "code": "not_found"}), 404

    rel = _repo_rel(full)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trash_dest = TRASH_DIR / date_str / rel

    # Handle collision with numeric suffix
    if trash_dest.exists():
        suffix = 1
        while True:
            candidate = trash_dest.parent / f"{trash_dest.name}.{suffix}"
            if not candidate.exists():
                trash_dest = candidate
                break
            suffix += 1

    try:
        trash_dest.parent.mkdir(parents=True, exist_ok=True)
        full.rename(trash_dest)
    except OSError as e:
        _audit("delete", rel, result="error", reason=str(e))
        return jsonify({"error": str(e), "code": "io_error"}), 500

    trashed_to = _repo_rel(trash_dest)
    _audit("delete", rel, trashed_to=trashed_to)
    return jsonify({"path": rel, "trashed_to": trashed_to, "op": "delete"})


@bp.route("/api/workspace/upload", methods=["POST"])
@login_required
@require_permission("workspace", "manage")
def workspace_upload():
    """Upload a file via multipart/form-data."""
    from werkzeug.utils import secure_filename

    path = request.form.get("path", "workspace")
    overwrite = request.form.get("overwrite", "false").lower() == "true"

    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "bad_path"}), 400

    f = request.files["file"]
    filename = secure_filename(f.filename or "upload")
    if not filename:
        return jsonify({"error": "Invalid filename", "code": "bad_path"}), 400

    # Check size before saving
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_UPLOAD_SIZE:
        return jsonify({"error": "File too large (max 50MB)", "code": "too_large"}), 413

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    dir_full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(dir_full))

    if not dir_full.is_dir():
        return jsonify({"error": "Target path is not a directory", "code": "bad_path"}), 400

    dest = dir_full / filename
    rel = _repo_rel(dest)

    if dest.exists() and not overwrite:
        return jsonify({"error": "File already exists", "code": "conflict"}), 409

    try:
        f.save(str(dest))
    except OSError as e:
        _audit("upload", rel, result="error", reason=str(e))
        return jsonify({"error": str(e), "code": "io_error"}), 500

    stat = dest.stat()
    _audit("upload", rel, bytes=stat.st_size, size=stat.st_size)
    return jsonify({"path": rel, "size": stat.st_size, "mtime": stat.st_mtime})


@bp.route("/api/workspace/download")
@login_required
@require_permission("workspace", "view")
def workspace_download():
    """Download a file with Content-Disposition: attachment."""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    require_admin = not _is_relative_to(
        (REPO_ROOT / path).resolve(), WORKSPACE_DIR.resolve()
    )
    full = _resolve_safe(path, require_admin=require_admin)
    _check_folder_access(_repo_rel(full))

    if not full.exists():
        return jsonify({"error": "File not found", "code": "not_found"}), 404
    if full.is_dir():
        return jsonify({"error": "Path is a directory", "code": "bad_path"}), 400

    is_admin_path = not _is_relative_to(full, WORKSPACE_DIR.resolve())
    if is_admin_path:
        _audit("download", _repo_rel(full), size=full.stat().st_size)

    inline = request.args.get("inline", "").lower() in ("1", "true")
    return send_file(str(full), as_attachment=not inline, download_name=full.name)


@bp.route("/api/workspace/recent")
@login_required
@require_permission("workspace", "view")
def workspace_recent():
    """List recent .md and .html files sorted by mtime descending.

    Compatibility shim replacing GET /api/reports consumed by any external caller.
    """
    limit = request.args.get("limit", 20, type=int)
    if limit < 1:
        limit = 1

    items = []
    if not WORKSPACE_DIR.is_dir():
        return jsonify({"items": []})

    for f in WORKSPACE_DIR.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".md", ".html"):
            continue
        if _is_blocklisted(f.name):
            continue
        rel_parts = f.relative_to(WORKSPACE_DIR).parts
        if any(_is_blocklisted(part) for part in rel_parts):
            continue
        # Enforce folder access: check top-level folder
        if rel_parts and not has_workspace_folder_access(current_user.role, f"workspace/{rel_parts[0]}"):
            continue
        try:
            stat = f.stat()
            mime, _ = mimetypes.guess_type(f.name)
            items.append({
                "path": _repo_rel(f),
                "name": f.name,
                "mime": mime or "text/plain",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
        except Exception:
            continue

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"items": items[:limit]})
