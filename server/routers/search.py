"""Search API — user-scoped semantic retrieval over context objects.

The original implementation was never mounted, assumed numeric Chroma ids and
queried the global collection with no ownership filter (cross-user leakage).
This rewrite:
  * scopes the vector query with where={"user_id": {"$in": [self, "global"]}}
  * joins against the DB for ownership + status filtering (authoritative),
    so a stale/archived vector can never surface an object the user may not see
  * keeps the progressive-disclosure output (compact / full / pack) and the
    temporal annotations of the original contract
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    layer: str = "compact"  # compact | full | pack
    include_stale: bool = False
    type: Optional[str] = None


@router.post("")
def semantic_search(req: SearchRequest, db: DBSession = Depends(get_db), user=Depends(get_current_user)):
    """Semantic search over the caller's context objects.

    Layer 'compact': id + type + status + score
    Layer 'full': compact + summary + body
    Layer 'pack': full + tags + timestamps (progressive disclosure)
    """
    from models.context_object import ContextObject
    import services.embedding_service as es

    top_k = max(1, min(req.top_k, 100))
    try:
        emb = es.get_embedding_service()
    except Exception as exc:
        logger.warning("embedding service unavailable: %s", exc)
        return {"ok": True, "results": [], "total": 0, "query": req.query,
                "time_aware": False, "time_range": None}

    # 1) vector candidates, scoped to this user + global/unowned objects
    try:
        raw = emb.search(req.query, top_k=top_k,
                         where={"user_id": {"$in": [str(user.id), "global"]}})
    except Exception as exc:
        logger.warning("vector search failed (falling back to empty): %s", exc)
        raw = []
    if not raw:
        return {"ok": True, "results": [], "total": 0, "query": req.query,
                "time_aware": False, "time_range": None}

    # 2) DB join is authoritative for ownership and status
    obj_ids = [r["id"] for r in raw]
    query = db.query(ContextObject).filter(
        ContextObject.id.in_(obj_ids),
        (ContextObject.user_id == user.id) | (ContextObject.user_id.is_(None)),
        ContextObject.status != "archived",
    )
    if not req.include_stale:
        query = query.filter(ContextObject.status == "active")
    if req.type:
        query = query.filter(ContextObject.type == req.type)
    objects = query.all()
    by_id = {o.id: o for o in objects}

    # 3) preserve vector ordering, skip ids the user cannot see
    results = []
    for r in raw:
        obj = by_id.get(r["id"])
        if obj is None:
            continue
        entry = {
            "id": obj.id,
            "score": round(r["score"], 4),
            "type": obj.type,
            "status": obj.status,
        }
        if req.layer in ("full", "pack"):
            entry["summary"] = (obj.summary or "")[:200]
            entry["body"] = (obj.body or "")[:500]
        if req.layer == "pack":
            entry["tags"] = obj.tags or []
            entry["title"] = obj.title
            entry["createdAt"] = str(obj.created_at) if obj.created_at else None
            entry["updatedAt"] = str(obj.updated_at) if obj.updated_at else None
        results.append(entry)

    # 4) temporal annotation (unchanged contract)
    from services.temporal_resolver import has_time_expression, resolve_time_range
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
