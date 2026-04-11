"""Providers endpoint — manage AI provider configurations (Anthropic, OpenRouter, OpenAI, Gemini, etc.).

EvoNexus supports multiple AI providers via OpenClaude. The active provider
determines which CLI binary (claude vs openclaude) and which env vars are
injected when spawning sessions.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_login import login_required

from routes._helpers import WORKSPACE

bp = Blueprint("providers", __name__)

PROVIDERS_CONFIG = WORKSPACE / "config" / "providers.json"

# Allowlisted CLI commands — only these binaries can be spawned
ALLOWED_CLI_COMMANDS = frozenset({"claude", "openclaude"})

# Allowlisted env var names — only these can be injected into subprocess
ALLOWED_ENV_VARS = frozenset({
    "CLAUDE_CODE_USE_OPENAI",
    "CLAUDE_CODE_USE_GEMINI",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "AWS_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "CLOUD_ML_REGION",
})


def _read_config() -> dict:
    """Read providers.json."""
    try:
        if PROVIDERS_CONFIG.is_file():
            return json.loads(PROVIDERS_CONFIG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {"active_provider": "anthropic", "providers": {}}


def _write_config(config: dict):
    """Write providers.json."""
    PROVIDERS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    PROVIDERS_CONFIG.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _mask_secret(value: str) -> str:
    """Mask an API key for safe display: sk-or-v1-abc...xyz → sk-or-****xyz."""
    if not value or len(value) < 8:
        return "****" if value else ""
    return value[:6] + "****" + value[-4:]


def _check_cli(command: str) -> dict:
    """Check if a CLI tool is installed. Only allowlisted commands are accepted."""
    if command not in ALLOWED_CLI_COMMANDS:
        return {"installed": False, "version": None, "path": None}
    bin_path = shutil.which(command)
    if not bin_path:
        return {"installed": False, "version": None, "path": None}
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return {"installed": True, "version": version, "path": bin_path}
    except (subprocess.TimeoutExpired, OSError):
        return {"installed": False, "version": None, "path": bin_path}


def _sanitize_env_vars(env_vars: dict) -> dict:
    """Filter env vars to only allowlisted names and safe values."""
    safe = {}
    for k, v in env_vars.items():
        if k not in ALLOWED_ENV_VARS:
            continue
        # Reject values with shell metacharacters
        if not isinstance(v, str) or re.search(r'[;&|`$\n\r]', v):
            continue
        safe[k] = v
    return safe


# ── Endpoints ──────────────────────────────────────────────


@bp.route("/api/providers")
@login_required
def list_providers():
    """List all providers with status info."""
    config = _read_config()
    active = config.get("active_provider", "anthropic")
    providers = config.get("providers", {})

    # Check CLI installation status for both binaries
    claude_status = _check_cli("claude")
    openclaude_status = _check_cli("openclaude")

    result = []
    for key, prov in providers.items():
        cli = prov.get("cli_command", "claude")
        if cli not in ALLOWED_CLI_COMMANDS:
            continue
        cli_status = claude_status if cli == "claude" else openclaude_status

        # Mask env var values for API response
        env_vars = prov.get("env_vars", {})
        masked_vars = {}
        for var_name, var_value in env_vars.items():
            if "KEY" in var_name or "SECRET" in var_name or "TOKEN" in var_name:
                masked_vars[var_name] = _mask_secret(var_value)
            else:
                masked_vars[var_name] = var_value

        # Check if provider has required env vars filled
        has_config = all(
            v != "" for k, v in env_vars.items()
            if k not in ("CLAUDE_CODE_USE_OPENAI", "CLAUDE_CODE_USE_GEMINI",
                         "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
        ) if env_vars else True

        result.append({
            "id": key,
            "name": prov.get("name", key),
            "description": prov.get("description", ""),
            "cli_command": cli,
            "is_active": key == active,
            "installed": cli_status["installed"],
            "version": cli_status["version"],
            "path": cli_status["path"],
            "has_config": has_config,
            "env_vars": masked_vars,
            "requires_logout": prov.get("requires_logout", False),
            "setup_hint": prov.get("setup_hint"),
            "default_model": prov.get("default_model"),
            "default_base_url": prov.get("default_base_url"),
            "default_region": prov.get("default_region"),
        })

    return jsonify({
        "providers": result,
        "active_provider": active,
        "claude_installed": claude_status["installed"],
        "openclaude_installed": openclaude_status["installed"],
    })


@bp.route("/api/providers/active", methods=["GET"])
@login_required
def get_active_provider():
    """Get the active provider."""
    config = _read_config()
    active = config.get("active_provider", "anthropic")
    provider = config.get("providers", {}).get(active, {})
    return jsonify({
        "active_provider": active,
        "name": provider.get("name", active),
        "cli_command": provider.get("cli_command", "claude"),
    })


@bp.route("/api/providers/active", methods=["POST"])
@login_required
def set_active_provider():
    """Set the active provider."""
    data = request.get_json(silent=True) or {}
    provider_id = data.get("provider_id")
    if not provider_id:
        return jsonify({"error": "provider_id is required"}), 400

    config = _read_config()
    if provider_id not in config.get("providers", {}):
        return jsonify({"error": f"Unknown provider: {provider_id}"}), 400

    config["active_provider"] = provider_id
    _write_config(config)

    return jsonify({"status": "ok", "active_provider": provider_id})


@bp.route("/api/providers/<provider_id>/config", methods=["GET"])
@login_required
def get_provider_config(provider_id):
    """Get a provider's config (env vars masked)."""
    config = _read_config()
    provider = config.get("providers", {}).get(provider_id)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_id}"}), 400

    env_vars = provider.get("env_vars", {})
    masked = {}
    for k, v in env_vars.items():
        if "KEY" in k or "SECRET" in k or "TOKEN" in k:
            masked[k] = _mask_secret(v)
        else:
            masked[k] = v

    return jsonify({
        "id": provider_id,
        "name": provider.get("name"),
        "env_vars": masked,
        "env_var_names": list(env_vars.keys()),
    })


@bp.route("/api/providers/<provider_id>/config", methods=["POST"])
@login_required
def update_provider_config(provider_id):
    """Update a provider's env vars."""
    data = request.get_json(silent=True) or {}
    new_env_vars = data.get("env_vars", {})

    config = _read_config()
    provider = config.get("providers", {}).get(provider_id)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_id}"}), 400

    # Merge: only update allowlisted vars that are provided and not masked
    existing = provider.get("env_vars", {})
    for key, value in new_env_vars.items():
        if key not in ALLOWED_ENV_VARS:
            continue
        if key not in existing:
            continue
        # Skip if value looks masked (contains ****)
        if "****" in str(value):
            continue
        # Reject values with shell metacharacters
        if not isinstance(value, str) or re.search(r'[;&|`$\n\r]', value):
            continue
        existing[key] = value

    provider["env_vars"] = existing
    _write_config(config)

    return jsonify({"status": "ok", "provider_id": provider_id})


@bp.route("/api/providers/<provider_id>/test", methods=["POST"])
@login_required
def test_provider(provider_id):
    """Test a provider by running its CLI with --version."""
    config = _read_config()
    provider = config.get("providers", {}).get(provider_id)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_id}"}), 400

    cli = provider.get("cli_command", "claude")
    if cli not in ALLOWED_CLI_COMMANDS:
        return jsonify({"success": False, "error": f"Unsupported CLI: {cli}"}), 400

    bin_path = shutil.which(cli)
    if not bin_path:
        return jsonify({
            "success": False,
            "error": f"'{cli}' not found in PATH",
            "hint": f"npm install -g {'@gitlawb/openclaude' if cli == 'openclaude' else '@anthropic-ai/claude-code'}",
        })

    # Build env with sanitized provider vars
    env_vars = _sanitize_env_vars(
        {k: v for k, v in provider.get("env_vars", {}).items() if v}
    )
    test_env = {**os.environ, **env_vars}

    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True, text=True, timeout=15,
            env=test_env,
        )
        return jsonify({
            "success": result.returncode == 0,
            "version": result.stdout.strip() or result.stderr.strip(),
            "cli": cli,
            "path": bin_path,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Command timed out"})
    except OSError as e:
        return jsonify({"success": False, "error": str(e)})
