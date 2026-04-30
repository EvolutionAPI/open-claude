"""Agent Knowledge routes.

This module provides an accounting-friendly facade over the pgvector Knowledge
engine. It keeps the canonical RAG divisions aligned with the custom accounting
agents while reusing the existing Knowledge ingestion/search pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import text
from werkzeug.utils import secure_filename

from routes.auth_routes import require_permission
from routes.knowledge import _assert_key, _get_sqlite, _require_xhr

from knowledge import documents as documents_mod
from knowledge import search as search_mod
from knowledge import spaces as spaces_mod
from knowledge.connection_pool import get_dsn, get_engine

bp = Blueprint("agent_knowledge", __name__)

_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "uploads"


AGENT_KNOWLEDGE_DIVISIONS: list[dict[str, Any]] = [
    {
        "slug": "geral",
        "label": "Geral",
        "agent": None,
        "description": "Base compartilhada entre todos os agentes contabeis.",
        "color": "#00FFA7",
    },
    {
        "slug": "custom-atendimento",
        "label": "Atendimento",
        "agent": "custom-atendimento",
        "description": "Triagem, comunicacao com clientes, pendencias e protocolos.",
        "color": "#38BDF8",
    },
    {
        "slug": "custom-controladoria",
        "label": "Controladoria",
        "agent": "custom-controladoria",
        "description": "Indicadores, fechamentos gerenciais, controles e analises.",
        "color": "#A78BFA",
    },
    {
        "slug": "custom-fiscal",
        "label": "Fiscal",
        "agent": "custom-fiscal",
        "description": "Tributos, notas, apuracoes, obrigacoes e legislacao fiscal.",
        "color": "#F59E0B",
    },
    {
        "slug": "custom-orquestrador",
        "label": "Orquestrador",
        "agent": "custom-orquestrador",
        "description": "Procedimentos gerais, roteamento de demandas e regras de operacao.",
        "color": "#00FFA7",
    },
    {
        "slug": "custom-rh",
        "label": "RH",
        "agent": "custom-rh",
        "description": "Folha, admissao, desligamento, beneficios e rotinas trabalhistas.",
        "color": "#F472B6",
    },
    {
        "slug": "custom-societario",
        "label": "Societario",
        "agent": "custom-societario",
        "description": "Contratos sociais, alteracoes, CNPJ, licencas e Junta Comercial.",
        "color": "#34D399",
    },
]

_DIVISION_BY_SLUG = {d["slug"]: d for d in AGENT_KNOWLEDGE_DIVISIONS}


def _error(code: str, message: str, status: int = 400):
    return jsonify({"error": code, "message": message}), status


def _connections() -> list[dict[str, Any]]:
    _assert_key()
    from knowledge.connections import list_connections

    conn = _get_sqlite()
    try:
        return list_connections(conn)
    finally:
        conn.close()


def _ready_connections() -> list[dict[str, Any]]:
    return [c for c in _connections() if c.get("status") == "ready"]


def _resolve_connection_id(preferred: str | None = None) -> tuple[str | None, list[dict[str, Any]]]:
    ready = _ready_connections()
    if preferred:
        for conn in ready:
            if preferred in {conn.get("id"), conn.get("slug")}:
                return conn["id"], ready
        raise ValueError(f"Knowledge connection '{preferred}' is not ready or does not exist.")
    if not ready:
        return None, ready
    return ready[0]["id"], ready


def _space_stats(connection_id: str, space_id: str) -> dict[str, int]:
    engine = get_engine(connection_id, get_dsn(connection_id))
    with engine.connect() as pg:
        row = pg.execute(
            text(
                """
                SELECT
                    COUNT(DISTINCT d.id) AS documents_count,
                    COUNT(c.id)          AS chunks_count
                FROM knowledge_spaces s
                LEFT JOIN knowledge_documents d ON d.space_id = s.id
                LEFT JOIN knowledge_chunks c ON c.space_id = s.id
                WHERE s.id = :space_id
                """
            ),
            {"space_id": space_id},
        ).fetchone()
    if row is None:
        return {"documents_count": 0, "chunks_count": 0}
    data = dict(row._mapping)
    return {
        "documents_count": int(data.get("documents_count") or 0),
        "chunks_count": int(data.get("chunks_count") or 0),
    }


def _space_payload(connection_id: str, division: dict[str, Any]) -> dict[str, Any]:
    space = spaces_mod.get_space_by_slug(connection_id, division["slug"])
    payload = {
        **division,
        "ready": bool(space),
        "space": space,
        "documents_count": 0,
        "chunks_count": 0,
    }
    if space:
        payload.update(_space_stats(connection_id, space["id"]))
    return payload


def _ensure_space(connection_id: str, division: dict[str, Any]) -> dict[str, Any]:
    existing = spaces_mod.get_space_by_slug(connection_id, division["slug"])
    if existing:
        return existing

    try:
        return spaces_mod.create_space(
            connection_id,
            {
                "slug": division["slug"],
                "name": division["label"],
                "description": division["description"],
                "visibility": "shared",
                "access_rules": {
                    "agent_knowledge": True,
                    "agent": division["agent"],
                },
                "content_type_boosts": {
                    "faq": 1.25,
                    "reference": 1.20,
                    "decision": 1.15,
                    "tutorial": 1.10,
                    "article": 1.00,
                    "note": 0.95,
                    "transcript": 0.85,
                },
            },
        )
    except Exception:
        # Concurrent first-run bootstrap may create the same slug between the
        # read and insert. Re-read before surfacing the original error.
        existing = spaces_mod.get_space_by_slug(connection_id, division["slug"])
        if existing:
            return existing
        raise


def _ensure_division(connection_id: str, slug: str) -> tuple[dict[str, Any], dict[str, Any]]:
    division = _DIVISION_BY_SLUG.get(slug)
    if not division:
        raise KeyError(f"Unknown division '{slug}'")
    return division, _ensure_space(connection_id, division)


def _get_division_space(connection_id: str, slug: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    division = _DIVISION_BY_SLUG.get(slug)
    if not division:
        raise KeyError(f"Unknown division '{slug}'")
    return division, spaces_mod.get_space_by_slug(connection_id, division["slug"])


def _document_status(document_id: str) -> dict[str, Any]:
    return documents_mod.get_ingestion_status(document_id) or {"document_id": document_id, "phase": "pending"}


@bp.route("/api/agent-knowledge/divisions", methods=["GET"])
@require_permission("knowledge", "view")
def divisions():
    try:
        connection_id, ready = _resolve_connection_id(request.args.get("connection_id"))
    except Exception as exc:
        return _error("connection_error", str(exc), 400)

    if not connection_id:
        return jsonify(
            {
                "connections": ready,
                "active_connection_id": None,
                "divisions": AGENT_KNOWLEDGE_DIVISIONS,
                "ready": False,
                "message": "No ready pgvector Knowledge connection configured.",
            }
        )

    try:
        return jsonify(
            {
                "connections": ready,
                "active_connection_id": connection_id,
                "divisions": [_space_payload(connection_id, d) for d in AGENT_KNOWLEDGE_DIVISIONS],
                "ready": True,
            }
        )
    except Exception as exc:
        return _error("divisions_failed", str(exc), 500)


@bp.route("/api/agent-knowledge/bootstrap", methods=["POST"])
@require_permission("knowledge", "manage")
def bootstrap():
    _require_xhr()
    data = request.get_json(silent=True) or {}
    try:
        connection_id, _ready = _resolve_connection_id(data.get("connection_id"))
        if not connection_id:
            return _error("no_connection", "No ready pgvector Knowledge connection configured.", 400)
        created = []
        for division in AGENT_KNOWLEDGE_DIVISIONS:
            before = spaces_mod.get_space_by_slug(connection_id, division["slug"])
            space = _ensure_space(connection_id, division)
            if before is None:
                created.append(space["slug"])
        return jsonify(
            {
                "status": "ready",
                "created": created,
                "divisions": [_space_payload(connection_id, d) for d in AGENT_KNOWLEDGE_DIVISIONS],
            }
        )
    except Exception as exc:
        return _error("bootstrap_failed", str(exc), 500)


@bp.route("/api/agent-knowledge/documents", methods=["GET"])
@require_permission("knowledge", "view")
def list_documents():
    try:
        connection_id, _ready = _resolve_connection_id(request.args.get("connection_id"))
        if not connection_id:
            return _error("no_connection", "No ready pgvector Knowledge connection configured.", 400)
        division_slug = request.args.get("division") or "all"
        limit = min(int(request.args.get("limit", 25)), 100)

        if division_slug == "all":
            documents = []
            for division in AGENT_KNOWLEDGE_DIVISIONS:
                space = spaces_mod.get_space_by_slug(connection_id, division["slug"])
                if not space:
                    continue
                for doc in documents_mod.list_documents(connection_id, space_id=space["id"], limit=limit):
                    documents.append({**doc, "division": division["slug"], "division_label": division["label"]})
            documents.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
            return jsonify({"documents": documents[:limit]})

        division, space = _get_division_space(connection_id, division_slug)
        if not space:
            return jsonify({"documents": []})
        documents = [
            {**doc, "division": division["slug"], "division_label": division["label"]}
            for doc in documents_mod.list_documents(connection_id, space_id=space["id"], limit=limit)
        ]
        return jsonify({"documents": documents})
    except KeyError as exc:
        return _error("bad_division", str(exc), 404)
    except Exception as exc:
        return _error("documents_failed", str(exc), 500)


@bp.route("/api/agent-knowledge/upload", methods=["POST"])
@require_permission("knowledge", "manage")
def upload():
    _require_xhr()
    try:
        connection_id, _ready = _resolve_connection_id(request.form.get("connection_id"))
        if not connection_id:
            return _error("no_connection", "No ready pgvector Knowledge connection configured.", 400)
        division_slug = request.form.get("division") or ""
        division, space = _ensure_division(connection_id, division_slug)
    except KeyError as exc:
        return _error("bad_division", str(exc), 404)
    except Exception as exc:
        return _error("upload_failed", str(exc), 500)

    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return _error("bad_request", "Missing uploaded files.", 400)

    raw_tags = request.form.get("tags") or ""
    extra_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    uploads = []
    tmp_dir = _UPLOAD_DIR
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        original_name = f.filename or "document"
        safe_name = secure_filename(original_name) or f"document-{uuid4().hex}"
        tmp_path = tmp_dir / f"{uuid4().hex}-{safe_name}"
        f.save(str(tmp_path))

        metadata = {
            "title": request.form.get("title") or Path(original_name).stem,
            "tags": ["agent-knowledge", division["slug"], *(extra_tags or [])],
            "owner_id": str(getattr(current_user, "id", "") or ""),
            "agent": division["agent"],
            "division": division["slug"],
            "mime_type": f.mimetype or None,
        }
        doc = documents_mod.upload_document(connection_id, space["id"], str(tmp_path), metadata)
        uploads.append(
            {
                "document": doc,
                "document_id": doc.get("id"),
                "filename": original_name,
                "division": division["slug"],
                "division_label": division["label"],
                "status": _document_status(doc.get("id")),
            }
        )

    return jsonify({"uploads": uploads}), 202


@bp.route("/api/agent-knowledge/documents/<document_id>/status", methods=["GET"])
@require_permission("knowledge", "view")
def status(document_id: str):
    return jsonify(_document_status(document_id))


@bp.route("/api/agent-knowledge/documents/<document_id>", methods=["DELETE"])
@require_permission("knowledge", "manage")
def delete_document(document_id: str):
    _require_xhr()
    try:
        connection_id, _ready = _resolve_connection_id(request.args.get("connection_id"))
        if not connection_id:
            return _error("no_connection", "No ready pgvector Knowledge connection configured.", 400)
        ok = documents_mod.delete_document(connection_id, document_id)
        if not ok:
            return _error("not_found", f"Document {document_id} not found.", 404)
        return jsonify({"status": "deleted", "document_id": document_id})
    except Exception as exc:
        return _error("delete_failed", str(exc), 500)


@bp.route("/api/agent-knowledge/search", methods=["GET"])
@require_permission("knowledge", "view")
def search():
    query = (request.args.get("q") or request.args.get("query") or "").strip()
    if not query:
        return _error("bad_request", "query is required", 400)

    try:
        connection_id, _ready = _resolve_connection_id(request.args.get("connection_id"))
        if not connection_id:
            return _error("no_connection", "No ready pgvector Knowledge connection configured.", 400)
        division_slug = request.args.get("division") or "all"
        top_k = min(int(request.args.get("top_k", 10)), 50)

        targets = []
        if division_slug == "all":
            for division in AGENT_KNOWLEDGE_DIVISIONS:
                space = spaces_mod.get_space_by_slug(connection_id, division["slug"])
                if space:
                    targets.append((division, space))
        else:
            division, space = _get_division_space(connection_id, division_slug)
            if not space:
                return jsonify({"query": query, "results": [], "total": 0})
            targets.append((division, space))

        results = []
        per_target_k = top_k if len(targets) <= 1 else max(3, top_k)
        for division, space in targets:
            hits = search_mod.hybrid_search(
                connection_id=connection_id,
                space_id=space["id"],
                query=query,
                top_k=per_target_k,
                filters={},
            )
            for hit in hits:
                results.append({**hit, "division": division["slug"], "division_label": division["label"]})

        results.sort(key=lambda r: float(r.get("final_score") or 0), reverse=True)
        return jsonify({"query": query, "results": results[:top_k], "total": len(results[:top_k])})
    except KeyError as exc:
        return _error("bad_division", str(exc), 404)
    except Exception as exc:
        return _error("search_failed", str(exc), 500)
