"""Tests for backend health endpoints."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace-root"
    (root / "dashboard" / "data").mkdir(parents=True, exist_ok=True)
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "providers.json").write_text(json.dumps({"active": "anthropic"}), encoding="utf-8")

    monkeypatch.setenv("EVONEXUS_SECRET_KEY", "test-secret-health")
    monkeypatch.setenv("EVONEXUS_ENV", "development")

    import routes.health as _health

    importlib.reload(_health)
    monkeypatch.setattr(_health, "WORKSPACE", root)
    return root


@pytest.fixture
def app(workspace, monkeypatch):
    import flask
    import models as _models
    import routes.health as _health

    importlib.reload(_models)
    importlib.reload(_health)
    monkeypatch.setattr(_health, "WORKSPACE", workspace)

    _app = flask.Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret-health"
    _app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    _app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    _models.db.init_app(_app)
    _app.register_blueprint(_health.bp)

    with _app.app_context():
        _models.db.create_all()

    return _app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_health_endpoint_reports_ok(client):
    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["filesystem"]["status"] == "ok"
    assert payload["checks"]["workspace"]["status"] == "ok"
    assert payload["checks"]["secret_key"]["status"] == "ok"


def test_live_health_endpoint(client):
    response = client.get("/api/health/live")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["process"]["status"] == "ok"


def test_ready_health_endpoint_includes_providers(client):
    response = client.get("/api/health/ready")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["checks"]["providers"]["status"] == "ok"
    assert payload["checks"]["providers"]["active"] == "anthropic"


def test_deep_health_includes_providers(client):
    response = client.get("/api/health/deep")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["checks"]["providers"]["status"] == "ok"
    assert payload["checks"]["providers"]["active"] == "anthropic"
