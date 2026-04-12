"""Config endpoint — CLAUDE.md, ROUTINES.md, ROADMAP.md, .env, commands, Makefile."""

import re
from flask import Blueprint, jsonify, request, Response, abort
from flask_login import login_required
from routes._helpers import WORKSPACE, safe_read

bp = Blueprint("config", __name__)


@bp.route("/api/config/workspace-status")
def workspace_status():
    """Check if workspace.yaml exists AND has owner configured."""
    config_path = WORKSPACE / "config" / "workspace.yaml"
    if not config_path.is_file():
        return jsonify({"configured": False})
    # File exists but check if owner is actually filled in
    try:
        content = config_path.read_text(encoding="utf-8")
        import yaml
        data = yaml.safe_load(content) or {}
        ws = data.get("workspace", data)
        owner = (ws.get("owner") or ws.get("owner_name") or "").strip()
        return jsonify({"configured": bool(owner)})
    except Exception:
        return jsonify({"configured": False})


@bp.route("/api/config/claude-md")
def get_claude_md():
    content = safe_read(WORKSPACE / "CLAUDE.md")
    if content is None:
        abort(404, description="CLAUDE.md not found")
    return Response(content, mimetype="text/markdown")


@bp.route("/api/config/routines")
def get_routines_md():
    # Try new name first, fallback to old
    content = safe_read(WORKSPACE / "ROUTINES.md")
    if content is None:
        abort(404, description="ROUTINES.md not found")
    return Response(content, mimetype="text/markdown")


# Legacy route alias
@bp.route("/api/config/routines")
def get_routines_legacy():
    return get_routines_md()


@bp.route("/api/config/roadmap")
def get_roadmap():
    content = safe_read(WORKSPACE / "ROADMAP.md")
    if content is None:
        abort(404, description="ROADMAP.md not found")
    return Response(content, mimetype="text/markdown")


@bp.route("/api/config/commands")
def list_commands():
    cmd_dir = WORKSPACE / ".claude" / "commands"
    if not cmd_dir.is_dir():
        return jsonify([])
    commands = []
    for f in sorted(cmd_dir.iterdir()):
        if f.suffix.lower() == ".md" and f.is_file():
            content = safe_read(f) or ""
            commands.append({
                "name": f.stem,
                "file": f.name,
                "content": content,
            })
    return jsonify(commands)


@bp.route("/api/config/env")
@login_required
def get_env():
    """Read .env file as structured key-value pairs."""
    content = safe_read(WORKSPACE / ".env")
    if content is None:
        return jsonify({"entries": [], "raw": ""})

    entries = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"type": "comment", "value": line})
        elif "=" in stripped:
            key, _, val = stripped.partition("=")
            entries.append({"type": "var", "key": key.strip(), "value": val.strip()})
        else:
            entries.append({"type": "comment", "value": line})

    return jsonify({"entries": entries, "raw": content})


@bp.route("/api/config/env", methods=["PUT"])
@login_required
def update_env():
    """Update .env file. Accepts {entries: [...]} or {raw: "..."}."""
    from models import has_permission, audit
    from flask_login import current_user

    if not has_permission(current_user.role, "config", "manage"):
        abort(403)

    data = request.get_json()
    env_path = WORKSPACE / ".env"

    if "raw" in data:
        # Raw text mode
        env_path.write_text(data["raw"])
    elif "entries" in data:
        # Structured mode
        lines = []
        for entry in data["entries"]:
            if entry.get("type") == "comment":
                lines.append(entry.get("value", ""))
            else:
                key = entry.get("key", "")
                val = entry.get("value", "")
                if key:
                    lines.append(f"{key}={val}")
        env_path.write_text("\n".join(lines) + "\n")

    # Reload dotenv in current process
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
    except Exception:
        pass

    audit(current_user, "env_updated", "config", "Updated .env file")
    return jsonify({"status": "saved"})


@bp.route("/api/config/makefile")
def parse_makefile():
    content = safe_read(WORKSPACE / "Makefile")
    if content is None:
        abort(404, description="Makefile not found")

    targets = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", line)
        if m:
            name = m.group(1)
            desc = ""
            if "##" in line:
                desc = line.split("##", 1)[1].strip()
            elif i > 0 and lines[i - 1].startswith("#"):
                desc = lines[i - 1].lstrip("# ").strip()
            targets.append({"name": name, "description": desc})

    return jsonify(targets)
