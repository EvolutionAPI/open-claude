from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import g, request


def _json_default(value: Any):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def emit_json_log(level: str, event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **fields,
    }
    stream = sys.stderr if level.lower() in {"warning", "error", "critical"} else sys.stdout
    print(json.dumps(payload, ensure_ascii=False, default=_json_default), file=stream, flush=True)


def install_request_logging(app, service: str = "dashboard") -> None:
    """Emit one structured JSON record for every API/WebSocket request."""

    @app.before_request
    def _start_request_timer():
        if request.path.startswith("/api/") or request.path.startswith("/ws/"):
            g._structured_started_at = time.perf_counter()

    @app.after_request
    def _log_request(response):
        if request.path.startswith("/api/") or request.path.startswith("/ws/"):
            started_at = getattr(g, "_structured_started_at", None)
            duration_ms = None
            if started_at is not None:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
            emit_json_log(
                "info",
                "http_request",
                service=service,
                method=request.method,
                path=request.path,
                status=response.status_code,
                duration_ms=duration_ms,
                remote_addr=request.headers.get("X-Forwarded-For", request.remote_addr),
            )
        return response
