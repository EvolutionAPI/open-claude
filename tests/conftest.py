"""Root conftest.py — pytest markers and shared fixtures for the dual-backend CI matrix.

Markers
-------
@pytest.mark.sqlite
    Test runs only when the active backend is SQLite.
    Skipped when DATABASE_URL points to Postgres.

@pytest.mark.postgres
    Test runs only when the active backend is Postgres.
    Skipped when DATABASE_URL is absent or points to SQLite.

Fixture
-------
db_backend
    Parametrised over ("sqlite", "postgres") when both are available.
    When only SQLite is available (CI sqlite job), the "postgres" parameter
    is skipped automatically.

Usage in tests
--------------
    import pytest

    @pytest.mark.sqlite
    def test_sqlite_only_behaviour():
        ...

    @pytest.mark.postgres
    def test_pg_isolation_level():
        ...

    def test_both_backends(db_backend):
        # runs twice when both backends are available
        engine = db_backend
        ...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Detect active backend
# ---------------------------------------------------------------------------
_DATABASE_URL: str = os.environ.get("DATABASE_URL", "") or ""
_IS_PG: bool = _DATABASE_URL.startswith("postgresql") or _DATABASE_URL.startswith("postgres://")
_IS_SQLITE: bool = not _IS_PG


# ---------------------------------------------------------------------------
# Register custom markers (suppresses PytestUnknownMarkWarning)
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sqlite: test runs only on SQLite backend")
    config.addinivalue_line("markers", "postgres: test runs only on PostgreSQL backend")


# ---------------------------------------------------------------------------
# Skip enforcement
# ---------------------------------------------------------------------------
def pytest_runtest_setup(item: pytest.Item) -> None:
    markers = {m.name for m in item.iter_markers()}

    if "sqlite" in markers and not _IS_SQLITE:
        pytest.skip("Skipped: test requires SQLite backend (DATABASE_URL points to Postgres)")

    if "postgres" in markers and not _IS_PG:
        pytest.skip("Skipped: test requires Postgres backend (DATABASE_URL not set or points to SQLite)")


# ---------------------------------------------------------------------------
# db_backend fixture
# ---------------------------------------------------------------------------
def _pg_available() -> bool:
    """Return True if the DATABASE_URL env var points to a reachable Postgres."""
    if not _IS_PG:
        return False
    try:
        from sqlalchemy import create_engine, text
        url = _DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _sqlite_engine(tmp_path: Path):
    from sqlalchemy import create_engine
    db_file = tmp_path / "test_evonexus.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    return engine


def _pg_engine():
    from sqlalchemy import create_engine
    url = _DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


@pytest.fixture(
    params=["sqlite", "postgres"],
    ids=["sqlite", "postgres"],
)
def db_backend(request: pytest.FixtureRequest, tmp_path: Path):
    """Parametrised fixture yielding a SQLAlchemy engine for each backend.

    The 'postgres' parameter is skipped if Postgres is not reachable.
    """
    backend = request.param

    if backend == "postgres":
        if not _pg_available():
            pytest.skip("Postgres not available (DATABASE_URL not set or unreachable)")
        yield _pg_engine()
    else:
        yield _sqlite_engine(tmp_path)
