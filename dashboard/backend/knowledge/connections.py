"""CRUD operations for knowledge_connections (host DB — SQLite or Postgres).

All functions take a SQLAlchemy Connection as the first argument so the same
code path works on the dashboard's SQLite backend and on the Postgres backend
selected via DATABASE_URL. Callers control transaction lifecycle.

Public API:
    list_connections(conn) -> list[dict]
    get_connection(conn, connection_id) -> dict | None
    create_connection(conn, data) -> dict
    update_connection(conn, connection_id, data) -> dict | None
    delete_connection(conn, connection_id) -> bool
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text


def _row_to_dict(row) -> Optional[Dict[str, Any]]:
    """Convert a SQLAlchemy Row to a dict, stripping the encrypted secret."""
    if row is None:
        return None
    d = dict(row._mapping)
    # connection_string_encrypted must never appear in API responses
    d.pop("connection_string_encrypted", None)
    return d


def list_connections(conn) -> List[Dict[str, Any]]:
    """Return all connections, ordered by created_at DESC."""
    result = conn.execute(
        text("SELECT * FROM knowledge_connections ORDER BY created_at DESC")
    )
    return [_row_to_dict(row) for row in result.fetchall()]


def get_connection(conn, connection_id: str) -> Optional[Dict[str, Any]]:
    """Return a single connection by id, or None if not found."""
    row = conn.execute(
        text("SELECT * FROM knowledge_connections WHERE id = :id"),
        {"id": connection_id},
    ).fetchone()
    return _row_to_dict(row) if row else None


def create_connection(conn, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new connection record.

    *data* fields:
      Required: name (str), slug (str)
      Optional: host, port, database_name, username, ssl_mode, connection_string_encrypted (bytes)
    Returns the created row (without connection_string_encrypted).
    Raises ValueError for duplicate slug.
    """
    connection_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        text("SELECT id FROM knowledge_connections WHERE slug = :slug"),
        {"slug": data["slug"]},
    ).fetchone()
    if existing:
        raise ValueError(f"A connection with slug '{data['slug']}' already exists.")

    conn.execute(
        text(
            """INSERT INTO knowledge_connections
               (id, slug, name, connection_string_encrypted, host, port,
                database_name, username, ssl_mode, status, created_at)
               VALUES (:id, :slug, :name, :cs, :host, :port,
                       :database_name, :username, :ssl_mode, :status, :created_at)"""
        ),
        {
            "id": connection_id,
            "slug": data["slug"],
            "name": data["name"],
            "cs": data.get("connection_string_encrypted"),
            "host": data.get("host"),
            "port": data.get("port"),
            "database_name": data.get("database_name"),
            "username": data.get("username"),
            "ssl_mode": data.get("ssl_mode"),
            "status": data.get("status", "disconnected"),
            "created_at": now,
        },
    )
    conn.commit()
    return get_connection(conn, connection_id)


def update_connection(
    conn, connection_id: str, data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Update mutable fields on an existing connection.

    Allowed fields: name, slug, host, port, database_name, username, ssl_mode,
    status, schema_version, pgvector_version, postgres_version,
    last_health_check, last_error, connection_string_encrypted.
    Returns the updated row, or None if not found.
    """
    mutable = {
        "name", "slug", "host", "port", "database_name", "username",
        "ssl_mode", "status", "schema_version", "pgvector_version",
        "postgres_version", "last_health_check", "last_error",
        "connection_string_encrypted",
    }
    updates = {k: v for k, v in data.items() if k in mutable}
    if not updates:
        return get_connection(conn, connection_id)

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = dict(updates)
    params["__id"] = connection_id
    conn.execute(
        text(f"UPDATE knowledge_connections SET {set_clause} WHERE id = :__id"),
        params,
    )
    conn.commit()
    return get_connection(conn, connection_id)


def delete_connection(conn, connection_id: str) -> bool:
    """Delete a connection. Returns True if a row was deleted."""
    result = conn.execute(
        text("DELETE FROM knowledge_connections WHERE id = :id"),
        {"id": connection_id},
    )
    conn.commit()
    return result.rowcount > 0


def get_connection_events(
    conn, connection_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Return recent events for a connection, newest first."""
    result = conn.execute(
        text(
            "SELECT id, connection_id, event_type, details, created_at "
            "FROM knowledge_connection_events "
            "WHERE connection_id = :cid ORDER BY created_at DESC LIMIT :lim"
        ),
        {"cid": connection_id, "lim": limit},
    )
    rows = []
    for row in result.fetchall():
        d = dict(row._mapping)
        if d.get("details") and isinstance(d["details"], str):
            try:
                d["details"] = json.loads(d["details"])
            except (json.JSONDecodeError, TypeError):
                pass
        rows.append(d)
    return rows
