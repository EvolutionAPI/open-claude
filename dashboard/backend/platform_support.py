from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parent.parent.parent
PLATFORM_DATA_DIR = WORKSPACE / "dashboard" / "data" / "platform"
PLATFORM_EVENTS_PATH = PLATFORM_DATA_DIR / "events.jsonl"
PROVIDER_METRICS_PATH = PLATFORM_DATA_DIR / "provider-metrics.jsonl"
INSTALLED_PLUGINS_PATH = PLATFORM_DATA_DIR / "installed-plugins.json"
PLUGIN_REGISTRY_PATH = WORKSPACE / "config" / "plugin-registry.json"


def ensure_platform_data_dir() -> Path:
    PLATFORM_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return PLATFORM_DATA_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_platform_data_dir()
    event = {"ts": _now_iso(), **payload}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except Exception:
        return []
    if limit is not None and limit >= 0:
        return rows[-limit:]
    return rows


def database_scheme(database_uri: str | None) -> str:
    if not database_uri:
        return "sqlite"
    if "://" not in database_uri:
        return "sqlite"
    return database_uri.split(":", 1)[0].lower()
