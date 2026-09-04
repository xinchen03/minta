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
