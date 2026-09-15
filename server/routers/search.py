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
import re

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
    # Ask the vector store for a wider candidate pool before DB filtering and
    # ranking.  Otherwise global onboarding cards can consume all top-k slots.
    candidate_k = min(max(top_k * 5, 25), 100)
    try:
        emb = es.get_embedding_service()
    except Exception as exc:
        logger.warning("embedding service unavailable: %s", exc)
        return {"ok": True, "results": [], "total": 0, "query": req.query,
                "time_aware": False, "time_range": None}

    # 1) vector candidates, scoped to this user + global/unowned objects
    try:
        raw = emb.search(req.query, top_k=candidate_k,
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

    # 3) Re-rank visible candidates.  Private objects get a small ownership
    # prior, while exact title/summary terms get a lexical boost that keeps a
    # long document's topic visible when generic global cards are similar.
    query_terms = set(re.findall(r"[a-z0-9$]+|[一-鿿]", req.query.lower()))
    def _overlap(text):
        terms = set(re.findall(r"[a-z0-9$]+|[一-鿿]", (text or "").lower()))
        return len(query_terms & terms) / max(len(query_terms), 1)

    results = []
    for r in raw:
        obj = by_id.get(r["id"])
        if obj is None:
            continue
        semantic_score = float(r.get("score", 0.0))
        lexical_score = _overlap(f"{obj.title} {obj.summary}")
        body_score = _overlap(obj.body)
        ownership_boost = 0.05 if obj.user_id == user.id else 0.0
        tags = obj.tags if isinstance(obj.tags, list) else []
        is_onboarding = "onboarding" in {str(tag).lower() for tag in tags}
        onboarding_penalty = -0.20 if is_onboarding and lexical_score == 0 else 0.0
        final_score = (semantic_score + 0.25 * lexical_score + 0.10 * body_score
                       + ownership_boost + onboarding_penalty)
        entry = {
            "id": obj.id,
            "score": round(final_score, 4),
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

    results.sort(key=lambda item: item["score"], reverse=True)
    results = results[:top_k]

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
