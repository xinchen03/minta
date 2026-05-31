"""Slot CRUD API — 7 predefined slots per user."""
from __future__ import annotations
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from config import get_db
from models.slot import Slot, DEFAULT_SLOTS
from models.audit_log import record_audit
from routers.auth import get_current_user, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/slots", tags=["slots"])


class SlotUpdate(BaseModel):
    content: str = ""
    pinned: Optional[bool] = None


class SlotBatchUpdate(BaseModel):
    label: str
    pinned: bool


def _ensure_defaults(db: DBSession, user_id: int):
    """Create default 7 slots for new users."""
    existing = db.query(Slot).filter(Slot.user_id == user_id).all()
    existing_labels = {s.label for s in existing}
    created = 0
    for tmpl in DEFAULT_SLOTS:
        if tmpl["label"] not in existing_labels:
            slot = Slot(
                user_id=user_id,
                label=tmpl["label"],
                content=tmpl.get("content", ""),
                size_limit=tmpl.get("size_limit", 2000),
                pinned=tmpl.get("pinned", True),
                scope=tmpl.get("scope", "global"),
            )
            db.add(slot)
            created += 1
    if created:
        db.commit()
        logger.info(f"Created {created} default slots for user {user_id}")


@router.get("")
def list_slots(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    _ensure_defaults(db, user.id)
    slots = db.query(Slot).filter(Slot.user_id == user.id).order_by(Slot.label).all()
    return [s.to_dict() for s in slots]


@router.get("/{label}")
def get_slot(label: str, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    _ensure_defaults(db, user.id)
    slot = db.query(Slot).filter(Slot.user_id == user.id, Slot.label == label).first()
    if not slot:
        raise HTTPException(status_code=404, detail=f"Slot '{label}' not found")
    return slot.to_dict()


@router.put("/{label}")
def update_slot(label: str, data: SlotUpdate, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    _ensure_defaults(db, user.id)
    slot = db.query(Slot).filter(Slot.user_id == user.id, Slot.label == label).first()
    if not slot:
        raise HTTPException(status_code=404, detail=f"Slot '{label}' not found")

    new_content = data.content
    if len(new_content) > slot.size_limit:
        from services.retention import smart_trim
        new_content, archived_text = smart_trim(new_content, slot.size_limit, db, user.id, label)
        if archived_text:
            logger.info(f"Slot '{label}' trimmed: {len(archived_text)} chars archived")

    slot.content = new_content
    if data.pinned is not None:
        slot.pinned = data.pinned
    slot.auto_reflected = False

    db.commit()
    db.refresh(slot)

    record_audit(db, user.id, "update", "slots.update_slot", "slot", [str(slot.id)], {
        "label": label,
        "contentLen": len(new_content),
        "pinned": slot.pinned,
    })

    return slot.to_dict()


@router.patch("/batch-pin")
def batch_update_pins(data: List[SlotBatchUpdate], user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    _ensure_defaults(db, user.id)
    updated = []
    for item in data:
        slot = db.query(Slot).filter(Slot.user_id == user.id, Slot.label == item.label).first()
        if slot:
            slot.pinned = item.pinned
            updated.append(item.label)
    db.commit()

    record_audit(db, user.id, "update", "slots.batch_update_pins", "slot", [], {
        "updatedLabels": updated,
    })

    return {"success": True, "updated": updated}


@router.delete("/{label}")
def clear_slot(label: str, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """Clear slot content (does NOT delete the slot record)."""
    slot = db.query(Slot).filter(Slot.user_id == user.id, Slot.label == label).first()
    if not slot:
        raise HTTPException(status_code=404, detail=f"Slot '{label}' not found")

    slot.content = ""
    slot.auto_reflected = False
    db.commit()

    record_audit(db, user.id, "delete", "slots.clear_slot", "slot", [str(slot.id)], {
        "label": label,
        "action": "clear_content",
    })

    return {"success": True, "message": f"Slot '{label}' cleared"}


@router.get("/pack/generate")
def generate_context_pack(user: User = Depends(get_current_user), scene: str = "auto", db: DBSession = Depends(get_db)):
    """Generate a Context Pack from pinned slots for AI injection.

    When MINTA_EXPERT_ENABLED=true, automatically includes matched expert
    production rules from the user's compiled CPG domains.
    """
    _ensure_defaults(db, user.id)

    slots = db.query(Slot).filter(
        Slot.user_id == user.id,
        Slot.pinned == True,  # noqa: E712
        Slot.content != "",
    ).all()

    # ── Minta Expert: lightweight directory (not full rules) ──
    expert_directory = None
    try:
        from config import MINTA_EXPERT_ENABLED
        if MINTA_EXPERT_ENABLED:
            from services.production_store import list_rules
            from collections import defaultdict
            all_rules = list_rules(db, user.id, domain=None, stage=None, limit=100)
            if all_rules:
                # Group by domain, extract metadata
                by_domain = defaultdict(lambda: {"count": 0, "sources": set(), "sample_trigger": ""})
                for r in all_rules:
                    d = r.domain or "unknown"
                    by_domain[d]["count"] += 1
                    if r.source:
                        by_domain[d]["sources"].add(r.source)
                    if not by_domain[d]["sample_trigger"] and r.trigger:
                        by_domain[d]["sample_trigger"] = r.trigger[:80]
                expert_directory = [
                    {
                        "domain": d,
                        "rule_count": info["count"],
                        "sources": list(info["sources"])[:2],
                        "sample": info["sample_trigger"],
                    }
                    for d, info in sorted(by_domain.items())
                ]
    except Exception:
        pass

    from services.brief_builder import build_context_pack
    pack = build_context_pack(slots, scene, expert_directory=expert_directory)
    return {"scene": scene, "content": pack, "slotCount": len(slots),
            "expertDomains": len(expert_directory) if expert_directory else 0}
