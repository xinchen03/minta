"""Session management API — track conversations and trigger reflection.

Endpoints:
  POST /api/sessions/start              — start a session
  POST /api/sessions/{id}/observe       — record observation during session
  POST /api/sessions/{id}/reflect       — trigger reflection at session end
  GET  /api/sessions                    — list recent sessions
  GET  /api/sessions/{id}               — get single session
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from config import get_db
from models.session import Session as SessionModel
from models.audit_log import record_audit
from routers.auth import get_current_user, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class ObservationPayload(BaseModel):
    type: str = ""
    content: str = ""
    tool_name: str = ""
    tool_output: str = ""


class ReflectPayload(BaseModel):
    observations: List[ObservationPayload] = []


class SessionCreate(BaseModel):
    session_id: str
    project_path: str = ""


# ── POST routes ──

@router.post("/start")
def start_session(data: SessionCreate, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    existing = db.query(SessionModel).filter(SessionModel.id == data.session_id).first()
    if existing:
        return {"success": True, "sessionId": existing.id, "created": False}

    session = SessionModel(
        id=data.session_id,
        user_id=user.id,
        project_path=data.project_path or "",
    )
    db.add(session)
    db.commit()
    record_audit(db, user.id, "create", "sessions.start_session", "session", [data.session_id])
    return {"success": True, "sessionId": session.id, "created": True}


@router.post("/{session_id}/observe")
def record_observation(
    session_id: str,
    data: ObservationPayload,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id, SessionModel.user_id == user.id,
    ).first()
    if not session:
        session = SessionModel(id=session_id, user_id=user.id)
        db.add(session)
        db.commit()

    session.observation_count = (session.observation_count or 0) + 1

    from services.reflect import detect_signals
    signals = detect_signals(data.content or data.tool_output or "")
    if signals:
        session.correction_count = (session.correction_count or 0) + sum(
            1 for s in signals if s["type"] == "correction"
        )
    db.commit()
    return {"success": True, "observationCount": session.observation_count, "signalsDetected": len(signals)}


@router.post("/{session_id}/reflect")
def trigger_reflection(
    session_id: str,
    data: ReflectPayload,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id, SessionModel.user_id == user.id,
    ).first()
    if not session:
        session = SessionModel(id=session_id, user_id=user.id)
        db.add(session)
        db.commit()

    from services.reflect import reflect_session
    obs_list = [o.dict() if hasattr(o, "dict") else o for o in (data.observations or [])]
    result = reflect_session(db, user.id, obs_list)

    session.summary = (
        f"Signals: {result['signals_detected']}, "
        f"Slots: {', '.join(result['slots_updated']) or 'none'}"
    )
    session.ended_at = datetime.utcnow()
    db.commit()

    record_audit(db, user.id, "reflect", "sessions.trigger_reflection", "session", [session_id], {
        "signalsDetected": result["signals_detected"],
        "slotsUpdated": result["slots_updated"],
    })
    return {"success": True, **result}


# ── GET routes ──

@router.get("")
def list_sessions(limit: int = 20, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == user.id)
        .order_by(SessionModel.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [s.to_dict() for s in sessions]


@router.get("/{session_id}")
def get_session(session_id: str, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id, SessionModel.user_id == user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()
