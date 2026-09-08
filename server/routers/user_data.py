"""User data export & deletion for privacy compliance.

Inventory: every user-scoped table + vector index (Chroma metadata) +
Autopilot JSONL logs + uploaded avatar file + eval-contract store.
Deletion purges all categories, revokes the user's API keys and login
sessions, and keeps the account row (per "account remains active" contract).
Errors are collected per category; a category that fails never blocks the
rest, and the response reports exactly which categories failed.
"""
from __future__ import annotations

import logging
import os
import base64
import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import get_db
from models.archived_item import ArchivedItem
from models.context_object import ContextObject
from models.inbox import InboxItem
from models.skill import Skill
from models.slot import Slot
from models.graph_edge import GraphEdge
from models.activity_log import ActivityLog
from models.inference_log import InferenceLog
from models.context_retrieval_log import ContextRetrievalLog
from models.task_reward_log import TaskRewardLog
from models.bandit_state import BanditState
from models.audit_log import AuditLog
from models.api_key import ApiKey
from models.session import Session as ProjectSession
from routers.auth import get_current_user, User
from routers.comments import Comment
from services.autopilot import decision_logger
from services import embedding_service

logger = logging.getLogger("minta.user_data")
router = APIRouter(prefix="/api/user", tags=["user_data"])

# ── inventory: every user-scoped table (extend here when a table appears) ──
CONTENT_TABLES = {
    "contextObjects": ContextObject,
    "inboxItems": InboxItem,
    "skills": Skill,
    "slots": Slot,
    "graphEdges": GraphEdge,
    "archivedItems": ArchivedItem,
    "activityLog": ActivityLog,
    "inferenceLog": InferenceLog,
    "contextRetrievalLog": ContextRetrievalLog,
    "taskRewardLog": TaskRewardLog,
    "banditState": BanditState,
    "comments": Comment,
    "auditLog": AuditLog,
    "sessions": ProjectSession,
}
# API key material is revoked on delete and never returned by export.
CREDENTIAL_TABLES = {"apiKeys": ApiKey}


def _row_dict(row) -> dict:
    if hasattr(row, "to_dict"):
        return row.to_dict()
    out = {}
    for col in row.__table__.columns:
        val = getattr(row, col.key)
        out[col.key] = val.isoformat() if isinstance(val, datetime) else val
    return out


def _purge_table(db: Session, model, user_id: int) -> int:
    rows = db.query(model).filter(model.user_id == user_id).all()
    for r in rows:
        db.delete(r)
    return len(rows)


def _eval_store_if_present():
    """Open the independent eval store without creating an absent SQLite DB."""
    from eval_store import EvalStore, DEFAULT_DB
    from sqlalchemy.engine import make_url

    db_url = os.environ.get("MINTA_EVAL_DB", DEFAULT_DB).rstrip("/")
    url = make_url(db_url)
    if url.drivername.startswith("sqlite"):
        database = url.database
        if database not in (None, "", ":memory:") and not Path(database).exists():
            return None
    return EvalStore(db_url)


def _export_avatar(user: User):
    if not user.avatar_url:
        return None
    from routers.upload import AVATAR_DIR

    name = os.path.basename(user.avatar_url)
    path = Path(AVATAR_DIR) / name
    result = {"url": user.avatar_url, "filename": name, "contentType": None,
              "contentBase64": None}
    if name and path.is_file():
        result["contentType"] = mimetypes.guess_type(name)[0]
        result["contentBase64"] = base64.b64encode(path.read_bytes()).decode("ascii")
    return result


@router.get("/export-data")
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Export all of the current user's data as JSON (content only, no secrets)."""
    data = {
        "exportedAt": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "experimentCondition": user.experiment_condition,
            "createdAt": str(user.created_at) if user.created_at else None,
        },
    }
    for label, model in CONTENT_TABLES.items():
        rows = db.query(model).filter(model.user_id == user.id).all()
        data[label] = [_row_dict(r) for r in rows]
    # Autopilot decision logs live in JSONL files, not a table
    try:
        data["autopilotLogs"] = decision_logger.query_logs(
            user_id=str(user.id), limit=None, strict=True)
    except Exception:
        logger.exception("Failed to export Autopilot logs for user %s", user.id)
        data["autopilotLogs"] = []
    try:
        store = _eval_store_if_present()
        data["evalData"] = (store.export_user_data(str(user.id)) if store else
                            {"addRequests": [], "memories": []})
    except Exception:
        logger.exception("Failed to export eval data for user %s", user.id)
        data["evalData"] = {"addRequests": [], "memories": []}
    try:
        data["vectors"] = embedding_service.get_embedding_service().export_user(user.id)
    except Exception:
        logger.exception("Failed to export vectors for user %s", user.id)
        data["vectors"] = []
    try:
        data["avatar"] = _export_avatar(user)
    except Exception:
        logger.exception("Failed to export avatar for user %s", user.id)
        data["avatar"] = None
    return data


@router.delete("/delete-data")
def delete_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete all of the current user's data. Profile remains."""
    counts: dict = {}
    errors: dict = {}

    for label, model in CONTENT_TABLES.items():
        try:
            counts[label] = _purge_table(db, model, user.id)
            db.commit()
        except Exception as e:
            db.rollback()
            errors[label] = type(e).__name__
            logger.exception("Failed to delete category %s for user %s", label, user.id)

    # revoke credentials (deletion of a credential row IS the revoke action)
    for label, model in CREDENTIAL_TABLES.items():
        try:
            counts[label] = _purge_table(db, model, user.id)
            db.commit()
        except Exception as e:
            db.rollback()
            errors[label] = type(e).__name__
            logger.exception("Failed to revoke category %s for user %s", label, user.id)

    # vector index (user-scoped metadata)
    try:
        counts["vectors"] = embedding_service.get_embedding_service().delete_user(user.id)
    except Exception as e:
        errors["vectors"] = type(e).__name__
        logger.exception("Failed to delete vectors for user %s", user.id)

    # Autopilot JSONL logs
    try:
        counts["autopilotLogs"] = decision_logger.delete_user_logs(user.id)
    except Exception as e:
        errors["autopilotLogs"] = type(e).__name__
        logger.exception("Failed to delete Autopilot logs for user %s", user.id)

    # uploaded avatar file + reference (user data, not account identity)
    try:
        counts["avatarFile"] = 0
        if user.avatar_url:
            from routers.upload import AVATAR_DIR
            name = os.path.basename(user.avatar_url)
            fp = os.path.join(str(AVATAR_DIR), name)
            if name and os.path.exists(fp):
                os.remove(fp)
                counts["avatarFile"] = 1
            user.avatar_url = None
            db.commit()
    except Exception as e:
        db.rollback()
        errors["avatarFile"] = type(e).__name__
        logger.exception("Failed to delete avatar for user %s", user.id)

    # eval-contract store (separate DB, own engine — skip when absent)
    try:
        store = _eval_store_if_present()
        deleted = store.delete_user_data(str(user.id)) if store else {
            "memories": 0, "addRequests": 0}
        counts["evalMemory"] = deleted["memories"] + deleted["addRequests"]
    except Exception as e:
        errors["evalMemory"] = type(e).__name__
        logger.exception("Failed to delete eval data for user %s", user.id)

    if errors:
        logger.warning("delete-data completed with partial errors: %s", errors)
    return {
        "success": not errors,
        "partial": bool(errors),
        "deleted": counts,
        "errors": errors,
        "message": ("All user data deleted. Your account remains active."
                    if not errors else
                    "Some data categories could not be deleted; retry or contact support."),
    }
