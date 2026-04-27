"""Tests for auth hardening: password policy and login throttling."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def app():
    import flask
    from flask_login import LoginManager
    import models as _models

    importlib.reload(_models)

    _app = flask.Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"
    _app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    _app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    _models.db.init_app(_app)

    login_manager = LoginManager()
    login_manager.init_app(_app)

    @login_manager.user_loader
    def load_user(user_id):
        return _models.User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return flask.jsonify({"error": "Authentication required"}), 401

    import auth_security as _auth_security
    import routes.auth_routes as _auth_routes

    importlib.reload(_auth_security)
    importlib.reload(_auth_routes)
    _app.register_blueprint(_auth_routes.bp)

    with _app.app_context():
        _models.db.create_all()
        _models.seed_roles()

        admin = _models.User(
            username="admin",
            email="admin@example.com",
            display_name="Admin",
            role="admin",
        )
        admin.set_password("Valid!123")
        _models.db.session.add(admin)

        alice = _models.User(
            username="alice",
            email="alice@example.com",
            display_name="Alice",
            role="viewer",
        )
        alice.set_password("Strong!234")
        _models.db.session.add(alice)
        _models.db.session.commit()

    return _app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def csrf_headers(client):
    response = client.get("/api/auth/csrf")
    token = response.get_json()["csrf_token"]
    return {**XHR_HEADERS, "X-CSRF-Token": token}


def login_admin(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Valid!123"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200


def test_password_policy_rejects_common_password():
    from auth_security import password_policy_violations

    violations = password_policy_violations("pass", username="admin", email="admin@example.com")

    assert any("at least 8 characters" in msg for msg in violations)
    assert any("uppercase" in msg for msg in violations)
    assert any("digit" in msg for msg in violations)
    assert any("special character" in msg for msg in violations)

    common_violations = password_policy_violations("password123", username="admin", email="admin@example.com")

    assert any("too common" in msg for msg in common_violations)


def test_password_policy_rejects_identity_substrings():
    from auth_security import password_policy_violations

    violations = password_policy_violations("Admin123!", username="admin", email="admin@example.com")

    assert violations == ["Password must not contain your username or email address"]


def test_create_user_rejects_weak_password(client):
    login_admin(client)

    response = client.post(
        "/api/users",
        json={
            "username": "bob",
            "password": "weak",
            "role": "viewer",
        },
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert b"Password must be at least 8 characters" in response.data


def test_login_requires_xhr_header(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Valid!123"},
    )

    assert response.status_code == 403


def test_login_requires_csrf_token(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Valid!123"},
        headers=XHR_HEADERS,
    )

    assert response.status_code == 403


def test_change_password_rejects_weak_password(client):
    login_admin(client)

    response = client.post(
        "/api/auth/change-password",
        json={
            "old_password": "Valid!123",
            "new_password": "weak",
        },
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert b"Password must be at least 8 characters" in response.data


def test_login_locks_after_repeated_failures(client, app):
    for attempt in range(4):
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": f"wrong-{attempt}"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-final"},
        headers=csrf_headers(client),
    )
    assert locked_response.status_code == 429

    from models import LoginThrottle, db

    with app.app_context():
        buckets = LoginThrottle.query.all()
        assert buckets
        for bucket in buckets:
            bucket.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()

    success = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Strong!234"},
        headers=csrf_headers(client),
    )
    assert success.status_code == 200

    with app.app_context():
        assert LoginThrottle.query.count() == 0


def test_login_requires_totp_when_enabled(client, app):
    from totp_security import generate_totp_code, generate_totp_secret
    from models import User, db

    secret = generate_totp_secret()
    with app.app_context():
      user = User.query.filter_by(username="alice").first()
      assert user is not None
      user.enable_totp(secret)
      db.session.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Strong!234"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 412
    assert response.get_json()["requires_totp"] is True

    code = generate_totp_code(secret)
    success = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "Strong!234", "totp_code": code},
        headers=csrf_headers(client),
    )
    assert success.status_code == 200
