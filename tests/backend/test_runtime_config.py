"""Tests for backend runtime config helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import runtime_config as _runtime_config


def test_cors_allowed_origins_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example, https://b.example")
    importlib.reload(_runtime_config)

    assert _runtime_config.cors_allowed_origins() == ["https://a.example", "https://b.example"]


def test_load_dashboard_runtime_config_creates_secret_file(tmp_path, monkeypatch):
    monkeypatch.delenv("EVONEXUS_SECRET_KEY", raising=False)
    monkeypatch.delenv("EVONEXUS_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)

    config = _runtime_config.load_dashboard_runtime_config(tmp_path)

    assert _runtime_config.sqlite_path_from_uri(config.database_uri) == tmp_path / "dashboard" / "data" / "evonexus.db"
    assert config.database_backend == "sqlite"
    assert config.cors_allowed_origins == "*"
    assert config.dashboard_port == 8080
    assert len(config.secret_key) == 64
    assert (tmp_path / "dashboard" / "data" / ".secret_key").exists()


def test_database_uri_prefers_sqlite_env(monkeypatch):
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///D:/tmp/custom.db")

    assert _runtime_config.database_uri() == "sqlite:///D:/tmp/custom.db"


def test_database_uri_prefers_database_url(monkeypatch):
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
    monkeypatch.delenv("EVONEXUS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/evonexus")

    importlib.reload(_runtime_config)

    assert _runtime_config.database_uri() == "postgresql://user:pass@localhost:5432/evonexus"


def test_database_backend_accepts_postgres_uri():
    assert _runtime_config.database_backend("postgresql://user:pass@localhost:5432/evonexus") == "postgresql"
    assert _runtime_config.database_backend("D:/tmp/custom.db") == "sqlite"


def test_resolve_secret_key_requires_env_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("EVONEXUS_ENV", "production")
    monkeypatch.delenv("EVONEXUS_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError):
        _runtime_config.resolve_secret_key(tmp_path)


def test_sqlite_path_from_uri():
    result = _runtime_config.sqlite_path_from_uri("sqlite:///D:/tmp/evonexus.db")

    assert result == Path("D:/tmp/evonexus.db")


def test_dashboard_port_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EVONEXUS_PORT", "9090")
    importlib.reload(_runtime_config)

    assert _runtime_config.dashboard_port(tmp_path) == 9090


def test_dashboard_port_prefers_port(monkeypatch, tmp_path):
    monkeypatch.delenv("EVONEXUS_PORT", raising=False)
    monkeypatch.delenv("DASHBOARD_PORT", raising=False)
    monkeypatch.setenv("PORT", "8181")
    importlib.reload(_runtime_config)

    assert _runtime_config.dashboard_port(tmp_path) == 8181
