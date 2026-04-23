"""Onboarding wizard endpoints."""

from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user
from models import db, User, BrainRepoConfig

bp = Blueprint("onboarding", __name__)

@bp.route("/api/onboarding/state")
@login_required
def get_state():
    """Return full onboarding state for frontend to restore correct step."""
    brain = BrainRepoConfig.query.filter_by(user_id=current_user.id).first()
    return jsonify({
        "onboarding_state": current_user.onboarding_state,
        "onboarding_completed_agents_visit": current_user.onboarding_completed_agents_visit,
        "brain_repo_configured": brain is not None and brain.github_token_encrypted is not None,
        "brain_repo": brain.to_dict() if brain else None,
    })

@bp.route("/api/onboarding/start", methods=["POST"])
@login_required
def start():
    current_user.onboarding_state = "pending"
    db.session.commit()
    return jsonify({"onboarding_state": "pending"})

@bp.route("/api/onboarding/complete", methods=["POST"])
@login_required
def complete():
    current_user.onboarding_state = "completed"
    db.session.commit()
    return jsonify({"onboarding_state": "completed"})

@bp.route("/api/onboarding/skip", methods=["POST"])
@login_required
def skip():
    current_user.onboarding_state = "skipped"
    db.session.commit()
    return jsonify({"onboarding_state": "skipped"})

@bp.route("/api/onboarding/provider", methods=["POST"])
@login_required
def set_provider():
    """Save selected provider during onboarding. Delegates to existing provider config."""
    data = request.get_json() or {}
    provider = data.get("provider", "")
    api_key = data.get("api_key", "")
    if not provider:
        abort(400, description="provider required")
    # Save to existing providers config (same pattern as providers route)
    try:
        from routes._helpers import WORKSPACE
        import json
        providers_file = WORKSPACE / "config" / "providers.json"
        providers_file.parent.mkdir(exist_ok=True)
        providers = {}
        if providers_file.exists():
            providers = json.loads(providers_file.read_text(encoding="utf-8"))
        if provider not in providers:
            providers[provider] = {}
        if api_key:
            providers[provider]["api_key"] = api_key
        providers[provider]["enabled"] = True
        providers_file.write_text(json.dumps(providers, indent=2), encoding="utf-8")
    except Exception as e:
        abort(500, description=str(e))
    return jsonify({"ok": True, "provider": provider})
