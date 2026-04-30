"""HTTP request security helpers shared by Flask blueprints."""

from __future__ import annotations

from flask import abort, request

from session_security import CSRF_HEADER_NAME, XHR_HEADER_NAME, XHR_HEADER_VALUE, issue_session_token

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

XHR_EXEMPT_PREFIXES = (
    "/api/knowledge/v1/",
    "/api/triggers/webhook/",
)


def should_require_xhr(path: str, method: str, authorization_header: str = "") -> bool:
    """Return True when a mutating API request must carry the XHR header."""

    if method.upper() not in MUTATING_METHODS:
        return False
    if not path.startswith("/api/"):
        return False
    if (authorization_header or "").strip().startswith("Bearer "):
        return False
    for prefix in XHR_EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def require_xhr(req=request) -> None:
    """Abort with 403 if a mutating request lacks the XHR and CSRF headers."""

    if not should_require_xhr(req.path, req.method, req.headers.get("Authorization", "")):
        return
    if req.headers.get(XHR_HEADER_NAME) != XHR_HEADER_VALUE:
        abort(403, description="CSRF check failed: X-Requested-With header missing.")
    expected = issue_session_token(force=False)
    if req.headers.get(CSRF_HEADER_NAME, "").strip() != expected:
        abort(403, description="CSRF check failed: invalid or missing CSRF token.")
