"""Inbox CRUD API router."""
import json
import re
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from config import get_db
from models.inbox import InboxItem
from models.context_object import ContextObject
from routers.auth import get_current_user, User

router = APIRouter(prefix="/api/inbox", tags=["inbox"])

VALID_TYPES = {
    "preference", "workflow", "project_context", "decision_criteria",
    "lesson_learned", "writing_style", "rule", "ai_brief", "work_profile",
}


def _slugify(title: str) -> str:
    base = title.lower().strip()
    base = re.sub(r"[^\w\s-]", "", base)
    base = re.sub(r"[\s_]+", "-", base)
    return base[:80] or "untitled"


@router.get("")
def get_inbox(status: str = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    all_items = db.query(InboxItem).filter(InboxItem.user_id == user.id).order_by(InboxItem.created_at.desc()).all()

    pending = [i.to_dict() for i in all_items if i.status == "pending"]
    archived = [i.to_dict() for i in all_items if i.status == "archived"]

    return {
        "pending": [
            {
                "id": i["id"],
                "text": i["text"],
                "type": i.get("type"),
                "confidence": i["confidence"],
                "tags": i["tags"],
                "createdAt": i["createdAt"],
            }
            for i in pending
        ],
        "archived": [
            {
                "title": i["text"].split("\n")[0][:80] if i["text"] else "",
                "body": "\n".join(i["text"].split("\n")[1:]) if i["text"] and "\n" in i["text"] else i["text"],
                "tags": i["tags"],
            }
            for i in archived
        ],
        "pendingCount": len(pending),
        "archivedCount": len(archived),
        "totalCount": len(all_items),
    }


@router.post("/archive")
def archive_items(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    indices = payload.get("ids", [])
    types_map: dict = payload.get("types", {})

    items = db.query(InboxItem).filter(InboxItem.id.in_(indices), InboxItem.user_id == user.id).all()
    created_objects = 0

    for item in items:
        item.status = "archived"
        assigned_type = types_map.get(str(item.id)) or types_map.get(item.id)

        if assigned_type and assigned_type in VALID_TYPES:
            item.type = assigned_type
            text = item.text or ""
            first_line = text.split("\n")[0][:200] if text else "Untitled"
            rest = "\n".join(text.split("\n")[1:]) if text and "\n" in text else ""

            base_id = _slugify(first_line)
            ts_suffix = str(int(time.time()))[-4:]
            obj_id = f"{base_id}-{ts_suffix}"

            obj = ContextObject(
                id=obj_id,
                user_id=user.id,
                type=assigned_type,
                title=first_line[:200],
                summary=rest[:300] if rest else first_line[:300],
                body=text,
                tags=item.tags or [],
                source="counter_example",
                status="active",
                confidence=int(item.confidence * 5) if item.confidence else 3,
            )
            db.add(obj)
            created_objects += 1

    db.commit()
    return {"success": True, "count": len(items), "createdObjects": created_objects}


@router.post("/discard")
def discard_items(indices: List[int], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(InboxItem).filter(InboxItem.id.in_(indices), InboxItem.user_id == user.id).all()
    for item in items:
        item.status = "discarded"
    db.commit()
    return {"success": True, "count": len(items)}


@router.post("/append")
def append_item(text: str, confidence: float = 0.7, type: Optional[str] = None, tags: Optional[List[str]] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = InboxItem(
        user_id=user.id,
        text=text,
        confidence=confidence,
        type=type if type and type in VALID_TYPES else None,
        status="pending",
        tags=tags or [],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"success": True, "id": item.id}


@router.put("/{item_id}")
def update_item(item_id: int, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(InboxItem).filter(InboxItem.id == item_id, InboxItem.user_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    if "text" in payload:
        item.text = payload["text"]
    if "type" in payload:
        t = payload["type"]
        item.type = t if t in VALID_TYPES else None
    if "confidence" in payload:
        item.confidence = payload["confidence"]
    if "tags" in payload:
        item.tags = payload["tags"]
    if "status" in payload:
        item.status = payload["status"]
    db.commit()
    db.refresh(item)
    return {"success": True, "id": item.id}
