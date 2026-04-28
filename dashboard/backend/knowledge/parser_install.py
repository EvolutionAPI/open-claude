"""Marker model download management (ADR-002).

Called by POST /api/knowledge/parsers/install when the user activates
the Knowledge Base and wants to use the default Marker parser.

Model download is NOT triggered automatically — the UI explicitly asks
the user to install parser models (one-time, ~500MB Surya models).

Sentinel file: ~/.cache/evonexus/marker_installed.ok
    Present → models cached; install endpoint returns "already_installed".
    Absent → download needed.

Progress file: ~/.cache/evonexus/marker_install.progress.json
    Written by the background download thread so the UI can poll
    /api/knowledge/parsers/status while a long install is running.
    The Surya model download regularly takes 10–30 minutes on a low-end
    VPS, which exceeded the gunicorn worker timeout when the request was
    handled synchronously — the worker was killed mid-download, the
    socket reset, and the UI re-rendered the "Install" button as if the
    install never happened (#44).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


log = logging.getLogger(__name__)

_SENTINEL = Path.home() / ".cache" / "evonexus" / "marker_installed.ok"
_PROGRESS_FILE = Path.home() / ".cache" / "evonexus" / "marker_install.progress.json"
_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None


def _read_progress() -> Optional[Dict[str, Any]]:
    if not _PROGRESS_FILE.exists():
        return None
    try:
        return json.loads(_PROGRESS_FILE.read_text())
    except Exception:
        return None


def _write_progress(payload: Dict[str, Any]) -> None:
    try:
        _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PROGRESS_FILE.write_text(json.dumps(payload))
    except Exception:
        log.exception("failed to write marker install progress")


def get_parser_status() -> Dict[str, Any]:
    """Return current parser installation status.

    Returns:
        {
            "marker_installed": bool,
            "models_cached": list[str],
            "cached_at": iso_timestamp | None,
            "install_in_progress": bool,
            "install_stage": str | None,
            "install_progress": float | None,   # 0.0-1.0
            "install_error": str | None,
            "install_started_at": iso_timestamp | None,
        }
    """
    installed = _SENTINEL.exists()
    cached_at = _SENTINEL.read_text().strip() if installed else None

    models_cached: List[str] = []
    if installed:
        # Best-effort: list HuggingFace cache entries for Surya/Marker models
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.exists():
            models_cached = [
                d.name for d in hf_cache.iterdir()
                if d.is_dir() and ("surya" in d.name.lower() or "marker" in d.name.lower())
            ]

    progress = _read_progress() or {}
    in_progress = bool(progress.get("running")) and not installed

    return {
        "marker_installed": installed,
        "models_cached": models_cached,
        "cached_at": cached_at,
        "install_in_progress": in_progress,
        "install_stage": progress.get("stage"),
        "install_progress": progress.get("progress"),
        "install_error": progress.get("error"),
        "install_started_at": progress.get("started_at"),
    }


def _run_download() -> None:
    """Background worker — downloads models and writes progress incrementally."""
    from knowledge.parsers.marker_parser import (
        download_marker_models as _download,
        MarkerNotInstalledError,
    )

    started_at = datetime.now(timezone.utc).isoformat()
    _write_progress({
        "running": True,
        "stage": "starting",
        "progress": 0.0,
        "started_at": started_at,
        "error": None,
    })

    def _cb(stage: str, progress: float) -> None:
        _write_progress({
            "running": True,
            "stage": stage,
            "progress": progress,
            "started_at": started_at,
            "error": None,
        })

    try:
        _download(_cb)
        _write_progress({
            "running": False,
            "stage": "done",
            "progress": 1.0,
            "started_at": started_at,
            "error": None,
        })
    except MarkerNotInstalledError as exc:
        log.error("marker install failed: %s", exc)
        _write_progress({
            "running": False,
            "stage": "error",
            "progress": 0.0,
            "started_at": started_at,
            "error": f"marker-pdf is not installed in the runtime: {exc}",
        })
    except Exception as exc:  # noqa: BLE001
        log.exception("marker install crashed")
        _write_progress({
            "running": False,
            "stage": "error",
            "progress": 0.0,
            "started_at": started_at,
            "error": f"{type(exc).__name__}: {exc}",
        })


def start_marker_install() -> Dict[str, Any]:
    """Start the Marker download in a background thread.

    Returns immediately with the current status. The caller polls
    GET /api/knowledge/parsers/status to follow progress.

    Idempotent: if already installed, returns ``already_installed``.
    If a download is already running, returns the current progress
    without starting a second thread.
    """
    global _THREAD

    if _SENTINEL.exists():
        return {
            "status": "already_installed",
            "cached_at": _SENTINEL.read_text().strip(),
        }

    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"status": "in_progress", **(_read_progress() or {})}

        _THREAD = threading.Thread(
            target=_run_download,
            name="marker-install",
            daemon=True,
        )
        _THREAD.start()
        # Give the thread a beat to write its first progress entry.
        time.sleep(0.1)
        return {"status": "started", **(_read_progress() or {})}


def download_marker_models(
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """Synchronous download — kept for tests and CLI use only.

    The HTTP route should call ``start_marker_install`` instead, since the
    download easily exceeds the gunicorn worker timeout.
    """
    from knowledge.parsers.marker_parser import download_marker_models as _download
    return _download(progress_callback)
