"""Transactional SQL migrator for plugins.

Executes install.{sqlite,postgres}.sql / uninstall.{sqlite,postgres}.sql
statement-by-statement within a real database transaction.

Two execution paths, dispatched by ``db.engine.dialect``:

* SQLite — opens a sqlite3.Connection directly, uses BEGIN IMMEDIATE +
  PRAGMA foreign_keys=ON. Zero behavior change from contract v0.
* Postgres — opens a SQLAlchemy connection via ``db.engine.get_engine()``,
  wraps the run in ``conn.begin()`` (real PG transaction), executes each
  statement with ``conn.exec_driver_sql()``. Catches SQLAlchemyError.

Statements are split with sqlparse, which understands $$-quoted plpgsql
function bodies and SQLite multi-statement triggers (BEGIN...END).

NEVER uses cursor.executescript() — that method auto-commits on every
semicolon and cannot be rolled back.

ADR reference: ADR-1 in [C]architecture-plugins.md
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3  # noqa — allowlisted: plugin DDL engine uses sqlite3 Connection API for transactional SQL execution
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import sqlparse
import sqlparse.tokens as T

logger = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class MigrationError(Exception):
    """Raised when a SQL migration statement fails (after rollback)."""

    def __init__(
        self,
        statement_index: int,
        statement_preview: str,
        sqlite_errno: Optional[int],
        sqlite_msg: str,
    ) -> None:
        self.statement_index = statement_index
        self.statement_preview = statement_preview  # first 200 chars
        self.sqlite_errno = sqlite_errno
        self.sqlite_msg = sqlite_msg
        super().__init__(f"stmt #{statement_index} failed: {sqlite_msg}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statement_index": self.statement_index,
            "statement_preview": self.statement_preview,
            "sqlite_errno": self.sqlite_errno,
            "sqlite_msg": self.sqlite_msg,
        }


# ---------------------------------------------------------------------------
# Statement parsing
# ---------------------------------------------------------------------------

def _is_only_comment_or_whitespace(stmt: sqlparse.sql.Statement) -> bool:
    """Return True if a parsed statement contains only comments/whitespace."""
    for token in stmt.flatten():
        if token.ttype not in (
            T.Comment.Single,
            T.Comment.Multiline,
            T.Whitespace,
            T.Newline,
            T.Punctuation,  # lone semicolons
            None,
        ):
            return False
    return True


def split_statements(sql_text: str) -> List[str]:
    """Parse SQL into individual executable statements using sqlparse.

    Handles:
    - -- line comments and /* block comments */
    - Semicolons inside string literals ('foo;bar')
    - Double-quoted identifiers ("col;name")
    - CTEs (WITH ... AS (...) SELECT ...)
    - Multi-statement triggers (CREATE TRIGGER ... BEGIN ... END)
    - Empty input → empty list

    Args:
        sql_text: Raw SQL content from install.sql or uninstall.sql.

    Returns:
        List of non-empty, non-comment SQL statement strings.
    """
    parsed = sqlparse.parse(sql_text)
    result = []
    for stmt in parsed:
        if _is_only_comment_or_whitespace(stmt):
            continue
        stripped = str(stmt).strip()
        if stripped:
            result.append(stripped)
    return result


# ---------------------------------------------------------------------------
# Transactional runner
# ---------------------------------------------------------------------------

def run_sql_transactional(
    conn: sqlite3.Connection,
    sql_text: str,
    audit_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """Execute SQL within a single BEGIN IMMEDIATE / COMMIT transaction.

    On any sqlite3.Error:
    1. ROLLBACK is issued.
    2. MigrationError is raised (so the caller gets statement_index + preview).

    On any other unexpected exception:
    3. ROLLBACK is attempted (best-effort).
    4. Exception is re-raised as-is.

    PRAGMA foreign_keys = ON is set before the transaction so FK violations
    raise sqlite3.IntegrityError and trigger rollback naturally.

    Args:
        conn: Open sqlite3.Connection (must NOT be in autocommit mode).
        sql_text: Raw SQL to execute.
        audit_cb: Optional callback receiving a dict per statement:
                  {"action": "sql_stmt", "index": int, "preview": str,
                   "success": bool, "error"?: str}

    Returns:
        List of executed statement records (empty if sql_text had no statements).

    Raises:
        MigrationError: If any statement fails (transaction rolled back).
    """
    # Enforce FK constraints so violations cause exceptions → rollback
    conn.execute("PRAGMA foreign_keys = ON")

    statements = split_statements(sql_text)
    if not statements:
        return []

    results: List[Dict[str, Any]] = []

    # BEGIN IMMEDIATE acquires a reserved lock upfront; prevents race with
    # another writer mid-transaction.
    conn.execute("BEGIN IMMEDIATE")
    try:
        for idx, stmt in enumerate(statements):
            preview = stmt[:200]
            try:
                cur = conn.execute(stmt)
                record = {
                    "index": idx,
                    "preview": preview,
                    "rows_affected": cur.rowcount,
                    "success": True,
                }
                results.append(record)
                if audit_cb:
                    audit_cb({"action": "sql_stmt", "index": idx,
                              "preview": preview, "success": True})
            except sqlite3.Error as exc:
                conn.rollback()
                errno = getattr(exc, "sqlite_errorcode", None)
                if audit_cb:
                    audit_cb({"action": "sql_stmt", "index": idx,
                              "preview": preview, "success": False,
                              "error": str(exc)})
                raise MigrationError(idx, preview, errno, str(exc)) from exc

        conn.commit()

    except MigrationError:
        raise  # already rolled back above
    except Exception:
        # Best-effort rollback for unexpected exceptions
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise

    return results


# ---------------------------------------------------------------------------
# Postgres execution path (SQLAlchemy)
# ---------------------------------------------------------------------------

def run_sql_transactional_pg(
    sql_text: str,
    audit_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """Postgres twin of ``run_sql_transactional``.

    Opens a SQLAlchemy connection via ``db.engine.get_engine()``, wraps the
    run in ``conn.begin()``, splits with sqlparse (handles $$-quoted plpgsql
    bodies), and executes each statement with ``exec_driver_sql``. On the
    first ``SQLAlchemyError`` the transaction is rolled back automatically
    by the context manager and ``MigrationError`` is raised.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from db.engine import get_engine

    statements = split_statements(sql_text)
    if not statements:
        return []

    results: List[Dict[str, Any]] = []
    engine = get_engine()
    with engine.connect() as conn:
        try:
            with conn.begin():
                for idx, stmt in enumerate(statements):
                    preview = stmt[:200]
                    try:
                        cur = conn.exec_driver_sql(stmt)
                        rowcount = getattr(cur, "rowcount", -1)
                        record = {
                            "index": idx,
                            "preview": preview,
                            "rows_affected": rowcount,
                            "success": True,
                        }
                        results.append(record)
                        if audit_cb:
                            audit_cb({"action": "sql_stmt", "index": idx,
                                      "preview": preview, "success": True})
                    except SQLAlchemyError as exc:
                        if audit_cb:
                            audit_cb({"action": "sql_stmt", "index": idx,
                                      "preview": preview, "success": False,
                                      "error": str(exc)})
                        # Re-raise to trigger conn.begin() rollback
                        raise MigrationError(idx, preview, None, str(exc)) from exc
        except MigrationError:
            raise

    return results


# ---------------------------------------------------------------------------
# Public API: install / uninstall
# ---------------------------------------------------------------------------

def _get_db():
    """Return a sqlite3.Connection on the active SQLite database.

    Used as the fallback connection for ``install_plugin_sql`` /
    ``uninstall_plugin_sql`` when no ``conn`` is passed in and the dialect
    is SQLite. Postgres callers go through ``run_sql_transactional_pg`` and
    never touch this function.
    """
    from db.engine import DATABASE_URL

    if DATABASE_URL.startswith("sqlite"):
        # sqlite:///<path>   →   <path>
        db_path = DATABASE_URL.split("///", 1)[-1]
        return sqlite3.connect(db_path)  # noqa — allowlisted

    raise RuntimeError(
        "_get_db() called on Postgres backend; callers must use "
        "run_sql_transactional_pg via the dialect-aware install/uninstall "
        "wrappers in this module."
    )


def _is_postgres() -> bool:
    """Return True iff the active SQLAlchemy engine is Postgres."""
    from db.engine import dialect
    return dialect.name == "postgresql"


def install_plugin_sql(
    slug: str,
    sql_path: Path,
    audit_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Run a plugin's install SQL transactionally on the active backend.

    Dispatches by ``db.engine.dialect``:
    * SQLite — uses ``run_sql_transactional`` against a ``sqlite3.Connection``
      (caller may pass one in for tests; otherwise we open one).
    * Postgres — uses ``run_sql_transactional_pg`` which opens its own
      SQLAlchemy connection. The ``conn`` argument is ignored on Postgres.
    """
    if not sql_path.exists():
        raise FileNotFoundError(f"install SQL not found: {sql_path}")

    sql_text = sql_path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(sql_text.encode()).hexdigest()

    logger.info("Installing SQL for plugin '%s' (sha256=%s...)", slug, sha256[:12])

    if _is_postgres():
        try:
            results = run_sql_transactional_pg(sql_text, audit_cb=audit_cb)
            logger.info(
                "Plugin '%s' SQL install (postgres): %d statement(s) committed",
                slug, len(results),
            )
            return results
        except MigrationError:
            logger.error(
                "Plugin '%s' SQL install (postgres) failed — transaction rolled back",
                slug,
            )
            raise

    # SQLite path
    own_conn = conn is None
    if own_conn:
        conn = _get_db()

    try:
        results = run_sql_transactional(conn, sql_text, audit_cb=audit_cb)
        logger.info(
            "Plugin '%s' SQL install (sqlite): %d statement(s) committed",
            slug, len(results),
        )
        return results
    except MigrationError:
        logger.error(
            "Plugin '%s' SQL install (sqlite) failed — transaction rolled back",
            slug,
        )
        raise
    finally:
        if own_conn:
            conn.close()


def uninstall_plugin_sql(
    slug: str,
    sql_path: Path,
    audit_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Run a plugin's uninstall SQL transactionally on the active backend.

    Dispatches the same way as :func:`install_plugin_sql`.
    """
    if not sql_path.exists():
        raise FileNotFoundError(f"uninstall SQL not found: {sql_path}")

    sql_text = sql_path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(sql_text.encode()).hexdigest()

    logger.info("Uninstalling SQL for plugin '%s' (sha256=%s...)", slug, sha256[:12])

    if _is_postgres():
        try:
            results = run_sql_transactional_pg(sql_text, audit_cb=audit_cb)
            logger.info(
                "Plugin '%s' SQL uninstall (postgres): %d statement(s) committed",
                slug, len(results),
            )
            return results
        except MigrationError:
            logger.error(
                "Plugin '%s' SQL uninstall (postgres) failed — transaction rolled back",
                slug,
            )
            raise

    # SQLite path
    own_conn = conn is None
    if own_conn:
        conn = _get_db()

    try:
        results = run_sql_transactional(conn, sql_text, audit_cb=audit_cb)
        logger.info(
            "Plugin '%s' SQL uninstall (sqlite): %d statement(s) committed",
            slug, len(results),
        )
        return results
    except MigrationError:
        logger.error(
            "Plugin '%s' SQL uninstall (sqlite) failed — transaction rolled back",
            slug,
        )
        raise
    finally:
        if own_conn:
            conn.close()
