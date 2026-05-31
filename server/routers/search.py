"""Search API — ChromaDB semantic search with progressive disclosure.

Distilled from Claude-Mem: 3-layer output (index → timeline → full details).
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user
from services.embedding_service import get_embedding_service
from services.temporal_resolver import has_time_expression, resolve_time_range
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    layer: str = "compact"  # compact | full | pack
    include_stale: bool = False


@router.post("")
def semantic_search(req: SearchRequest, db: DBSession = Depends(get_db), user=Depends(get_current_user)):
    """Semantic search with progressive disclosure layers.

    Layer 'compact': id + type + score (minimal tokens)
    Layer 'full': compact + summary + body
    Layer 'pack': full + gap analysis context
    """
    from models.context_object import ContextObject

    emb = get_embedding_service()
    emb._ensure_init()

    # Semantic search
    raw = emb.search(req.query, top_k=req.top_k)
    if not raw:
        return {"ok": True, "results": [], "total": 0}

    # Fetch from DB for full metadata
    obj_ids = [int(r["id"]) for r in raw if r["id"].isdigit()]
    db_objects = {}
    if obj_ids:
        objects = db.query(ContextObject).filter(
            ContextObject.id.in_(obj_ids),
            ContextObject.user_id == user.id,
        ).all()
        db_objects = {obj.id: obj for obj in objects}

    # Assemble results
    results = []
    for r in raw:
        oid = r["id"]
        obj = db_objects.get(int(oid)) if oid.isdigit() else None
        entry = {
            "id": oid,
            "score": round(r["score"], 4),
            "type": obj.type if obj else "unknown",
            "status": obj.status if obj else "active",
        }
        if req.layer in ("full", "pack"):
            entry["summary"] = (obj.summary or "")[:200] if obj else ""
            entry["body"] = (obj.body or "")[:500] if obj else ""
        results.append(entry)

    # Temporal annotation
    time_aware = has_time_expression(req.query)
    time_range = resolve_time_range(req.query) if time_aware else None

    return {
        "ok": True,
        "results": results,
        "total": len(results),
        "query": req.query,
        "time_aware": time_aware,
        "time_range": [str(time_range[0]), str(time_range[1])] if time_range else None,
    }
