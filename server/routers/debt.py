"""Context Debt API — Memory Health metrics for public demo."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import get_db
from models.context_object import ContextObject
from routers.auth import get_current_user, User
from services.decay_engine import (
    compute_retention, initial_relevance_from_confidence, THETA_S,
)
from services.conflict_detector import (
    parse_embedding, cosine_similarity, compute_conflict_prob,
    check_negation_bypass, THETA_C, THETA_R,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/debt", tags=["debt"])


@router.get("/status")
def debt_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict:
    """Memory Health: staleness, redundancy, conflict metrics."""
    now = datetime.now(timezone.utc)
    objects = db.query(ContextObject).filter(
        ContextObject.user_id == user.id, ContextObject.status == "active",
    ).all()

    n = len(objects)
    if n == 0:
        return {"pool_size": 0, "D_S": 0.0, "D_R": 0.0, "D_C": 0.0}

    retentions = {}
    embeddings = {}
    for obj in objects:
        r0 = initial_relevance_from_confidence(obj.confidence or 3)
        last = obj.last_used_at or obj.updated_at or now
        retentions[obj.id] = compute_retention(
            initial_relevance=r0, last_access=last, context_type=str(obj.type), now=now)
        emb = parse_embedding(obj.embedding_384)
        if emb is not None:
            embeddings[obj.id] = emb

    stale_count = sum(1 for r in retentions.values() if r < THETA_S)
    D_S = round(stale_count / n, 4)

    redundant_ids = set()
    obj_ids = list(embeddings.keys())
    for i in range(len(obj_ids)):
        for j in range(i + 1, len(obj_ids)):
            if cosine_similarity(embeddings[obj_ids[i]], embeddings[obj_ids[j]]) > THETA_R:
                redundant_ids.add(obj_ids[i])
                redundant_ids.add(obj_ids[j])
    D_R = round(len(redundant_ids) / n, 4) if n > 0 else 0.0

    text_map = {obj.id: f"{obj.title or ''} {obj.summary or ''} {obj.body or ''}" for obj in objects}
    conflict_pairs = 0
    total_pairs = n * (n - 1) // 2
    if total_pairs > 0:
        for i in range(len(obj_ids)):
            for j in range(i + 1, len(obj_ids)):
                ci, cj = obj_ids[i], obj_ids[j]
                ei, ej = embeddings.get(ci), embeddings.get(cj)
                if ei is None or ej is None:
                    continue
                sim = cosine_similarity(ei, ej)
                b_ij = check_negation_bypass(text_map.get(ci, ""), text_map.get(cj, ""))
                if sim > THETA_R and not b_ij:
                    continue
                if retentions.get(ci, 0) < THETA_S or retentions.get(cj, 0) < THETA_S:
                    continue
                p = compute_conflict_prob(ei, ej,
                    getattr(next((o for o in objects if o.id == ci), None), "created_at", now),
                    getattr(next((o for o in objects if o.id == cj), None), "created_at", now))
                if p > THETA_C:
                    conflict_pairs += 1
        D_C = round(conflict_pairs / total_pairs, 4)
    else:
        D_C = 0.0

    # D_V: Schema violation ratio (public-safe, no calibrated params)
    from services.lifecycle_scanner import scan_schema_validation
    schema_findings = scan_schema_validation(db, user.id)
    D_V = round(len(schema_findings) / n, 4) if n > 0 else 0.0
    health = round(max(0, 100 - (D_S + D_R + D_C + D_V) * 100))

    return {
        "pool_size": n,
        "D_S": D_S, "D_R": D_R, "D_C": D_C, "D_V": D_V,
        "stale_count": stale_count,
        "redundant_objects": len(redundant_ids),
        "conflict_pairs": conflict_pairs,
        "schema_violations": len(schema_findings),
        "health_score": health,
        "health_label": "good" if health >= 80 else "fair" if health >= 60 else "poor" if health >= 40 else "critical",
    }
