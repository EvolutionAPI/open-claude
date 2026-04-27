from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from flask import abort, request, session


CSRF_SESSION_KEY = "_evonexus_csrf_token"
CSRF_ISSUED_AT_KEY = "_evonexus_csrf_issued_at"
CSRF_HEADER_NAME = "X-CSRF-Token"
XHR_HEADER_NAME = "X-Requested-With"
XHR_HEADER_VALUE = "XMLHttpRequest"


def _rotation_minutes() -> int:
    raw = os.environ.get("EVONEXUS_SESSION_KEY_ROTATION_MINUTES", "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 24 * 60
    return value if value > 0 else 24 * 60


def _parse_issued_at(raw: object) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def issue_session_token(force: bool = False) -> str:
    """Return the current per-session CSRF token, rotating it when needed."""

    token = session.get(CSRF_SESSION_KEY)
    issued_at = _parse_issued_at(session.get(CSRF_ISSUED_AT_KEY))
    age_minutes = None
    if issued_at is not None:
        age_minutes = (datetime.now(timezone.utc) - issued_at).total_seconds() / 60.0

    if force or not token or age_minutes is None or age_minutes >= _rotation_minutes():
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
        session[CSRF_ISSUED_AT_KEY] = datetime.now(timezone.utc).isoformat()

    return str(token)


def current_session_token() -> str | None:
    token = session.get(CSRF_SESSION_KEY)
    return str(token) if token else None


def attach_session_token(response):
    token = issue_session_token(force=False)
    response.headers[CSRF_HEADER_NAME] = token
    expose = response.headers.get("Access-Control-Expose-Headers", "")
    exposed = [item.strip() for item in expose.split(",") if item.strip()]
    if CSRF_HEADER_NAME not in exposed:
        exposed.append(CSRF_HEADER_NAME)
    response.headers["Access-Control-Expose-Headers"] = ", ".join(exposed)
    return response


def require_csrf_token(req=request) -> None:
    expected = issue_session_token(force=False)
    provided = req.headers.get(CSRF_HEADER_NAME, "").strip()
    if not provided or provided != expected:
        abort(403, description="CSRF check failed: invalid or missing CSRF token.")


def force_rotate_session_token() -> str:
    return issue_session_token(force=True)
