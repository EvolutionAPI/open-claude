"""Chat messages endpoint — idempotent insert + rewind.

PG mode: inserts into agent_chat_sessions + agent_chat_messages.
Auth: covered by the global Bearer token middleware in app.py (no per-route decorator needed).

seq assignment strategy:
    agent_chat_messages.seq is BigInteger nullable=True in the migration (not BIGSERIAL).
    We compute it client-side as MAX(seq)+1 per session inside the same transaction.
    This is safe because each Claude session is single-writer; the ON CONFLICT (id) DO NOTHING
    guard prevents duplicates even if two retries race.
"""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from db.engine import get_engine

bp = Blueprint("chat_messages", __name__)


@bp.route("/api/chat-messages", methods=["POST"])
def create_chat_message():
    """Idempotent insert via UUID PK.

    Body: {agent_name, session_id, role, text, blocks, files, uuid, ts}

    Returns 201 with {id, seq, duplicate: false} on insert,
    or {id, seq, duplicate: true} when the UUID already exists.
    """
    data = request.get_json(silent=True) or {}
    required = ("session_id", "role", "uuid")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing: {missing}"}), 400

    engine = get_engine()
    with engine.begin() as conn:
        # Upsert session — create if not exists, bump last_activity_at otherwise
        conn.execute(
            text("""
                INSERT INTO agent_chat_sessions (id, agent_name, last_activity_at)
                VALUES (:sid, :agent, NOW())
                ON CONFLICT (id) DO UPDATE SET last_activity_at = NOW()
            """),
            {"sid": data["session_id"], "agent": data.get("agent_name", "unknown")},
        )

        # Check for duplicate first (ON CONFLICT DO NOTHING won't RETURN on conflict)
        existing = conn.execute(
            text("SELECT seq FROM agent_chat_messages WHERE id = :id"),
            {"id": data["uuid"]},
        ).fetchone()

        if existing is not None:
            return jsonify({"id": data["uuid"], "seq": existing.seq, "duplicate": True}), 201

        # Compute next seq within the session (single-writer per session — safe)
        next_seq = conn.execute(
            text(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_chat_messages"
                " WHERE session_id = :sid"
            ),
            {"sid": data["session_id"]},
        ).scalar()

        # Encode JSON columns
        blocks_val = json.dumps(data["blocks"]) if data.get("blocks") is not None else None
        files_val = json.dumps(data["files"]) if data.get("files") is not None else None
        ts_val = data.get("ts") or None

        conn.execute(
            text("""
                INSERT INTO agent_chat_messages
                    (id, session_id, seq, role, text, blocks, files, ts)
                VALUES (
                    :id, :sid, :seq, :role, :text, :blocks, :files,
                    COALESCE(CAST(:ts AS TIMESTAMPTZ), NOW())
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": data["uuid"],
                "sid": data["session_id"],
                "seq": next_seq,
                "role": data["role"],
                "text": data.get("text"),
                "blocks": blocks_val,
                "files": files_val,
                "ts": ts_val,
            },
        )

    return jsonify({"id": data["uuid"], "seq": next_seq, "duplicate": False}), 201


@bp.route("/api/chat-messages/rewind", methods=["POST"])
def rewind_chat_message():
    """Soft-delete via rewound_at.

    Body: {session_id, at_uuid}

    Sets rewound_at = NOW() on the message with at_uuid and all subsequent
    messages (by seq) in the same session that have not already been rewound.
    Returns {rewound_count}.
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    at_uuid = data.get("at_uuid")
    if not session_id or not at_uuid:
        return jsonify({"error": "Missing session_id or at_uuid"}), 400

    engine = get_engine()
    with engine.begin() as conn:
        # Find the seq of the anchor message
        row = conn.execute(
            text(
                "SELECT seq FROM agent_chat_messages"
                " WHERE id = :id AND session_id = :sid"
            ),
            {"id": at_uuid, "sid": session_id},
        ).fetchone()
        if not row:
            return jsonify({"error": "Message not found"}), 404
        cut_seq = row.seq

        # Soft-delete anchor + all subsequent messages still visible
        result = conn.execute(
            text("""
                UPDATE agent_chat_messages
                SET rewound_at = NOW()
                WHERE session_id = :sid
                  AND seq >= :seq
                  AND rewound_at IS NULL
            """),
            {"sid": session_id, "seq": cut_seq},
        )

    return jsonify({"rewound_count": result.rowcount}), 200
