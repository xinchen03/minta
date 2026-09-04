"""Best-effort vector indexing hooks for the business app (fail-open).

Every context-object write path (create / update / delete / archive, inbox
archive, user starter seed) calls these helpers so the Chroma collection stays
in sync with the DB. A vector failure must never fail the request: all calls
are guarded and only logged.

Isolation: `metadata["user_id"]` is written on every vector; search must pass
a matching `where` (see routers/search.py). `user_id=None` indexes as
"global" (public / unowned objects, visible to everyone).

Env: MINTA_EMBEDDING_ENABLED=0 disables all hooks (tests / offline mode).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("minta.vector_ops")


def _service():
    from services import embedding_service  # lazy: heavy deps import late
    return embedding_service.get_embedding_service()


def enabled() -> bool:
    return os.environ.get("MINTA_EMBEDDING_ENABLED", "1").lower() not in ("0", "false", "off")


def compose_text(title: str = "", summary: str = "", body: str = "") -> str:
    """One indexable text per object; title first (most objects have no body)."""
    return " ".join(part.strip() for part in (title, summary, body) if part and part.strip())[:2000]


def index_object(obj_id: str, text: str, user_id=None, type_: str = "", status: str = "active") -> None:
    if not enabled() or not obj_id or not text.strip():
        return
    try:
        _service().add_vector(
            obj_id, text,
            metadata={
                "user_id": str(user_id) if user_id is not None else "global",
                "type": type_ or "",
                "status": status or "active",
            })
    except Exception:
        logger.warning("vector index failed for %s (continuing)", obj_id, exc_info=True)


def drop_object(obj_id: str) -> None:
    if not enabled() or not obj_id:
        return
    try:
        _service().delete_vectors([obj_id])
    except Exception:
        logger.warning("vector delete failed for %s (continuing)", obj_id, exc_info=True)


_conflict_warned = False


def apply_conflict_embedding(obj) -> None:
    """Fill `obj.embedding_384` (MiniLM 384-d, JSON float array) on write.

    This is the input column conflict_detector / lifecycle_scanner / debt /
    facts read — it has never been populated in either codebase, leaving the
    flagship "detect contradictions" feature inert. Called right before the
    object's commit. Fail-open: a missing/corrupt MiniLM model must never
    break a write (column simply stays NULL).
    """
    global _conflict_warned
    if os.environ.get("MINTA_CONFLICT_EMBED", "1").lower() in ("0", "false", "off"):
        return
    text = compose_text(getattr(obj, "title", ""),
                        getattr(obj, "summary", ""),
                        getattr(obj, "body", ""))
    if not text.strip():
        return
    try:
        from services import embedding_service
        import json as _json

        vec = embedding_service.get_conflict_embedding()(text[:1000])
        obj.embedding_384 = _json.dumps([float(x) for x in vec])
    except Exception:
        if not _conflict_warned:
            _conflict_warned = True
            logger.warning(
                "conflict embedding unavailable — embedding_384 stays empty "
                "(continuing)", exc_info=True)
