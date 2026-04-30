from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

import yaml


WORKSPACE = Path(__file__).resolve().parent.parent.parent


def is_production() -> bool:
    env = (
        os.environ.get("EVONEXUS_ENV")
        or os.environ.get("FLASK_ENV")
        or os.environ.get("ENV")
        or ""
    ).strip().lower()
    return env in {"production", "prod"}


def cors_allowed_origins() -> list[str] | str:
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        if raw == "*":
            return "*"
        origins = [origin.strip() for origin in re.split(r"[,\s]+", raw) if origin.strip()]
        return origins or "*"
    return "*" if not is_production() else []


def database_uri(workspace: Path = WORKSPACE) -> str:
    for key in ("SQLALCHEMY_DATABASE_URI", "EVONEXUS_DATABASE_URL", "DATABASE_URL"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return raw
    return f"sqlite:///{workspace / 'dashboard' / 'data' / 'evonexus.db'}"


def database_backend(database_uri_value: str) -> str:
    if "://" not in database_uri_value:
        return "sqlite"
    return (database_uri_value.split(":", 1)[0] or "sqlite").lower()


def sqlite_path_from_uri(database_uri_value: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_uri_value.startswith(prefix):
        return None
    return Path(database_uri_value.removeprefix(prefix))


def dashboard_port(workspace: Path = WORKSPACE) -> int:
    for key in ("EVONEXUS_PORT", "DASHBOARD_PORT", "PORT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                port = int(raw)
                if 1 <= port <= 65535:
                    return port
            except ValueError:
                pass

    config_path = workspace / "config" / "workspace.yaml"
    if config_path.is_file():
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            dashboard_cfg = cfg.get("dashboard", {}) if isinstance(cfg, dict) else {}
            for candidate in (dashboard_cfg.get("port"), cfg.get("port") if isinstance(cfg, dict) else None):
                if candidate is None:
                    continue
                port = int(candidate)
                if 1 <= port <= 65535:
                    return port
        except Exception:
            pass

    return 8080


def resolve_secret_key(workspace: Path = WORKSPACE) -> str:
    """Resolve the dashboard secret key from env or the local fallback file."""

    secret_key = os.environ.get("EVONEXUS_SECRET_KEY", "").strip()
    if secret_key:
        return secret_key

    if is_production():
        raise RuntimeError("EVONEXUS_SECRET_KEY must be set in production")

    key_file = workspace / "dashboard" / "data" / ".secret_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()

    secret_key = secrets.token_hex(32)
    key_file.write_text(secret_key, encoding="utf-8")
    key_file.chmod(0o600)
    return secret_key


@dataclass(frozen=True)
class DashboardRuntimeConfig:
    secret_key: str
    database_uri: str
    database_backend: str
    cors_allowed_origins: list[str] | str
    dashboard_port: int


def load_dashboard_runtime_config(workspace: Path = WORKSPACE) -> DashboardRuntimeConfig:
    db_uri = database_uri(workspace)
    return DashboardRuntimeConfig(
        secret_key=resolve_secret_key(workspace),
        database_uri=db_uri,
        database_backend=database_backend(db_uri),
        cors_allowed_origins=cors_allowed_origins(),
        dashboard_port=dashboard_port(workspace),
    )
