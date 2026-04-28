"""Knowledge connection health check — runs every 5 minutes per connection.

Implements ADR-005: drift detection on a heartbeat (5 min interval).
Also verifies connectivity and updates last_health_check timestamp.

Public API:
    check_connection_health(connection_id, connection_string, sqlite_conn) -> dict
    start_health_check_thread(get_app_fn)    — background 5-min scheduler
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text

from .connection_pool import get_engine

_INTERVAL_S = 300  # 5 minutes

_hc_lock = threading.Lock()
_hc_started = False
_hc_timer = None


# ---------------------------------------------------------------------------
# Single connection health check
# ---------------------------------------------------------------------------

def check_connection_health(
    connection_id: str,
    connection_string: str,
    host_conn,
) -> Dict[str, Any]:
    """Test connectivity + drift for one connection.

    Returns {"status": str, "latency_ms": float, ...}.
    Updates knowledge_connections in the host DB (SQLite or Postgres).

    ``host_conn`` is a SQLAlchemy Connection bound to the EvoNexus host DB.
    """
    from .auto_migrator import check_drift, get_alembic_head

    start = time.monotonic()
    now_ts = datetime.now(timezone.utc).isoformat()

    try:
        engine = get_engine(connection_id, connection_string)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = (time.monotonic() - start) * 1000

        # Update last_health_check
        host_conn.execute(
            text("UPDATE knowledge_connections SET last_health_check = :ts, last_error = NULL WHERE id = :id"),
            {"ts": now_ts, "id": connection_id},
        )
        host_conn.commit()

        # Drift check (ADR-005)
        drift_result = check_drift(connection_id, connection_string, host_conn)

        return {
            "status": "needs_migration" if drift_result.get("needs_migration") else "ready",
            "latency_ms": round(latency_ms, 2),
            "drift": drift_result,
        }

    except Exception as exc:
        host_conn.execute(
            text(
                "UPDATE knowledge_connections SET last_health_check = :ts, "
                "last_error = :err, status = :st WHERE id = :id"
            ),
            {
                "ts": now_ts,
                "err": str(exc)[:500],
                "st": "disconnected",
                "id": connection_id,
            },
        )
        host_conn.commit()
        return {"status": "disconnected", "error": str(exc)}


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------

def _run_health_checks(get_app_fn) -> None:
    """Run health checks for all 'ready' or 'needs_migration' connections.

    Uses the shared SQLAlchemy engine (works in SQLite and Postgres).
    """
    try:
        app = get_app_fn()
        with app.app_context():
            from .crypto import decrypt_secret

            # Lazy import to avoid circular deps at module load time.
            import sys
            backend_dir = str(Path(__file__).resolve().parents[1])
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            from db.engine import get_engine as _get_host_engine  # noqa: E402

            host_engine = _get_host_engine()
            with host_engine.connect() as host_conn:
                rows = host_conn.execute(
                    text(
                        "SELECT id, connection_string_encrypted FROM knowledge_connections "
                        "WHERE status IN ('ready', 'needs_migration', 'disconnected')"
                    )
                ).fetchall()
                for row in rows:
                    cid, cs_enc = row[0], row[1]
                    if cs_enc is None:
                        continue
                    try:
                        cs = decrypt_secret(bytes(cs_enc))
                        check_connection_health(cid, cs, host_conn)
                    except Exception:
                        pass
    except Exception:
        pass


def _hc_loop(get_app_fn) -> None:
    _run_health_checks(get_app_fn)
    _schedule_hc(get_app_fn)


def _schedule_hc(get_app_fn) -> None:
    global _hc_timer
    _hc_timer = threading.Timer(_INTERVAL_S, _hc_loop, args=(get_app_fn,))
    _hc_timer.daemon = True
    _hc_timer.start()


def start_health_check_thread(get_app_fn) -> None:
    """Start the background health check scheduler (idempotent).

    Runs the first pass on a short-delay timer (not inline) so app startup
    isn't blocked by slow/unreachable Postgres connections. Without this
    initial pass, the classify_worker would spam the log for up to
    _INTERVAL_S (5 min) on boot if a connection is offline, because stale
    status='ready' from the last session won't be reconciled until the
    first scheduled tick.
    """
    global _hc_started, _hc_timer
    with _hc_lock:
        if _hc_started:
            return
        _hc_started = True
    _hc_timer = threading.Timer(5.0, _hc_loop, args=(get_app_fn,))
    _hc_timer.daemon = True
    _hc_timer.start()
