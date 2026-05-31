"""Context Objects CRUD API router."""
import json
import re
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from config import get_db
from models.context_object import ContextObject
from models.context_retrieval_log import ContextRetrievalLog
from models.activity_log import ActivityLog
from routers.auth import get_current_user, User

router = APIRouter(prefix="/api/contextObjects", tags=["context_objects"])


def _slugify(title: str) -> str:
    """Generate a URL-safe id from a title."""
    base = title.lower().strip()
    base = re.sub(r"[^\w\s-]", "", base)
    base = re.sub(r"[\s_]+", "-", base)
    return base[:80] or "untitled"


@router.get("/stats")
def get_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    objects = db.query(ContextObject).filter(
        (ContextObject.user_id == user.id) | (ContextObject.user_id.is_(None))
    ).all()
    total = len(objects)

    # Type distribution
    type_dist = {}
    for obj in objects:
        type_dist[obj.type] = type_dist.get(obj.type, 0) + 1

    # Status distribution
    status_dist = {}
    for obj in objects:
        status_dist[obj.status] = status_dist.get(obj.status, 0) + 1

    # Timeline: group by month
    timeline = {}
    for obj in objects:
        if obj.created_at:
            month_key = obj.created_at.strftime("%Y-%m")
            timeline[month_key] = timeline.get(month_key, 0) + 1

    return {
        "total": total,
        "typeDistribution": [{"type": k, "count": v} for k, v in sorted(type_dist.items())],
        "statusDistribution": [{"status": k, "count": v} for k, v in sorted(status_dist.items())],
        "timeline": [{"month": k, "count": v} for k, v in sorted(timeline.items())],
    }


@router.get("")
def list_objects(type: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(ContextObject).filter(
        (ContextObject.user_id == user.id) | (ContextObject.user_id.is_(None))
    )
    if type:
        query = query.filter(ContextObject.type == type)
    objects = query.order_by(ContextObject.updated_at.desc()).all()
    result = [obj.to_dict() for obj in objects]

    # Auto-log retrieval + activity for experiment tracking
    try:
        db.add(ActivityLog(user_id=user.id, event_type="context_view", detail=f"{len(objects)} objects"))
        db.commit()
    except Exception:
        db.rollback()

    if user.experiment_condition:
        ranked_ids = [obj.id for obj in objects[:20]]
        log = ContextRetrievalLog(
            user_id=user.id,
            session_id=f"view-{user.id}-{int(datetime.utcnow().timestamp())}",
            ranked_context_ids=json.dumps(ranked_ids),
            scores=json.dumps([1.0 - i * 0.01 for i in range(len(ranked_ids))]),
            k_shown=len(ranked_ids),
            exp_condition=user.experiment_condition,
            context_count=len(objects),
            policy="bm25",
        )
        db.add(log)
        db.commit()

    return result


@router.get("/public")
def list_public_objects(type: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Get publicly shared context objects (community feed for card draw)."""
    query = db.query(ContextObject).filter(ContextObject.is_public == 1, ContextObject.status == "active")
    if type:
        query = query.filter(ContextObject.type == type)
    objects = query.order_by(ContextObject.updated_at.desc()).limit(limit).all()
    return [obj.to_dict() for obj in objects]


@router.post("")
def create_object(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = payload.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    obj_type = payload.get("type", "preference")
    if obj_type not in (
        "preference", "workflow", "project_context", "decision_criteria",
        "lesson_learned", "writing_style", "rule", "ai_brief", "work_profile",
    ):
        raise HTTPException(status_code=400, detail=f"invalid type: {obj_type}")

    import time
    base_id = _slugify(title)
    ts_suffix = str(int(time.time()))[-4:]
    obj_id = f"{base_id}-{ts_suffix}"

    obj = ContextObject(
        id=obj_id,
        user_id=user.id,
        type=obj_type,
        title=title,
        summary=payload.get("summary", ""),
        body=payload.get("body", ""),
        tags=payload.get("tags", []),
        source=payload.get("source", "manual"),
        status=payload.get("status", "active"),
        confidence=payload.get("confidence", 3),
        cover_image=payload.get("coverImage"),
        is_public=payload.get("isPublic", False),
        owner_name=payload.get("ownerName", user.username),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj.to_dict()


@router.patch("/{obj_id}")
def update_object(obj_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update a context object (title, summary, body, tags, is_public, etc.)."""
    obj = db.query(ContextObject).filter(ContextObject.id == obj_id, ContextObject.user_id == user.id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="not found")

    if "title" in payload:
        obj.title = payload["title"]
    if "summary" in payload:
        obj.summary = payload["summary"]
    if "body" in payload:
        obj.body = payload["body"]
    if "tags" in payload:
        obj.tags = payload["tags"]
    if "isPublic" in payload:
        obj.is_public = payload["isPublic"]
    obj.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(obj)
    return obj.to_dict()


@router.delete("/{obj_id}")
def delete_object(obj_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    obj = db.query(ContextObject).filter(ContextObject.id == obj_id, ContextObject.user_id == user.id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(obj)
    db.commit()
    return {"success": True, "id": obj_id}
