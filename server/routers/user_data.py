"""User data export & deletion for privacy compliance."""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from config import get_db
from models.context_object import ContextObject
from models.inbox import InboxItem
from models.skill import Skill
from routers.auth import get_current_user, User

router = APIRouter(prefix="/api/user", tags=["user_data"])


@router.get("/export-data")
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Export all of the current user's data as JSON."""
    context_objects = db.query(ContextObject).filter(ContextObject.user_id == user.id).all()
    inbox_items = db.query(InboxItem).filter(InboxItem.user_id == user.id).all()
    skills = db.query(Skill).filter(Skill.user_id == user.id).all()

    return {
        "exportedAt": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "experimentCondition": user.experiment_condition,
            "createdAt": str(user.created_at) if user.created_at else None,
        },
        "contextObjects": [o.to_dict() for o in context_objects],
        "inboxItems": [i.to_dict() for i in inbox_items],
        "skills": [s.to_dict() for s in skills],
    }


@router.delete("/delete-data")
def delete_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete all of the current user's data. Profile remains."""
    counts = {}

    objs = db.query(ContextObject).filter(ContextObject.user_id == user.id).all()
    counts["contextObjects"] = len(objs)
    for o in objs:
        db.delete(o)

    items = db.query(InboxItem).filter(InboxItem.user_id == user.id).all()
    counts["inboxItems"] = len(items)
    for i in items:
        db.delete(i)

    sk = db.query(Skill).filter(Skill.user_id == user.id).all()
    counts["skills"] = len(sk)
    for s in sk:
        db.delete(s)

    db.commit()
    return {
        "success": True,
        "deleted": counts,
        "message": "All user data deleted. Your account remains active.",
    }
