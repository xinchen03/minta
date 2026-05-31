"""Skills API router — CRUD + community sharing."""
import re
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from config import get_db
from models.skill import Skill
from routers.auth import get_current_user, User

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _slugify(name: str) -> str:
    base = name.lower().strip()
    base = re.sub(r"[^\w\s-]", "", base)
    base = re.sub(r"[\s_]+", "-", base)
    return base[:60] or "skill"


@router.get("/public")
def list_public_skills(group: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Get publicly shared skills (community feed)."""
    query = db.query(Skill).filter(Skill.is_public == 1)
    if group:
        query = query.filter(Skill.group == group)
    skills = query.order_by(Skill.group, Skill.name).limit(limit).all()
    return [s.to_dict() for s in skills]


@router.get("")
def list_skills(group: Optional[str] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Skill).filter(Skill.user_id == user.id)
    if group:
        query = query.filter(Skill.group == group)
    skills = query.order_by(Skill.group, Skill.name).all()
    return [s.to_dict() for s in skills]


@router.get("/groups")
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    skills = db.query(Skill).filter(Skill.user_id == user.id).all()
    groups = sorted(set(s.group for s in skills))
    return [{"name": g, "count": sum(1 for s in skills if s.group == g)} for g in groups]


@router.post("")
def create_skill(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    base_id = _slugify(name)
    ts_suffix = str(int(time.time()))[-4:]
    skill_id = f"{base_id}-{ts_suffix}"

    skill = Skill(
        id=skill_id,
        user_id=user.id,
        name=name,
        name_zh=payload.get("nameZh", name),
        group=payload.get("group", "general"),
        color=payload.get("color", ""),
        icon_bg=payload.get("iconBg", ""),
        icon=payload.get("icon", ""),
        description=payload.get("description", ""),
        tags=payload.get("tags", []),
        is_public=payload.get("isPublic", False),
        owner_name=user.username,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill.to_dict()


@router.patch("/{skill_id}")
def update_skill(skill_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.user_id == user.id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not found")

    if "name" in payload:
        skill.name = payload["name"]
    if "nameZh" in payload:
        skill.name_zh = payload["nameZh"]
    if "group" in payload:
        skill.group = payload["group"]
    if "description" in payload:
        skill.description = payload["description"]
    if "tags" in payload:
        skill.tags = payload["tags"]
    if "isPublic" in payload:
        skill.is_public = payload["isPublic"]

    db.commit()
    db.refresh(skill)
    return skill.to_dict()


@router.delete("/{skill_id}")
def delete_skill(skill_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.user_id == user.id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(skill)
    db.commit()
    return {"success": True, "id": skill_id}


@router.post("/{skill_id}/share")
def share_skill(skill_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Toggle public sharing for a skill."""
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.user_id == user.id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="not found")
    skill.is_public = payload.get("isPublic", True)
    skill.owner_name = user.username
    db.commit()
    db.refresh(skill)
    return {"success": True, "id": skill_id, "isPublic": bool(skill.is_public)}
