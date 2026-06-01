"""SQLAlchemy model for audit_log table + record_audit helper."""
from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy import Column, String, Text, Integer, Enum as SAEnum, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from config import Base

logger = logging.getLogger(__name__)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    action = Column(
        SAEnum(
            "create", "delete", "update", "evolve", "reflect",
            "export", "archive", "unarchive",
            name="audit_action",
        ),
        nullable=False,
    )
    source_function = Column(String(128), nullable=False)
    target_type = Column(
        SAEnum(
            "slot", "inbox_item", "context_object", "session", "skill",
            name="audit_target_type",
        ),
        nullable=False,
    )
    target_ids = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "action": self.action,
            "sourceFunction": self.source_function,
            "targetType": self.target_type,
            "targetIds": self.target_ids if isinstance(self.target_ids, list) else json.loads(str(self.target_ids or "[]")),
            "payload": self.payload if isinstance(self.payload, dict) else {},
            "createdAt": str(self.created_at) if self.created_at else "",
        }


def record_audit(
    db: Session,
    user_id: int,
    action: str,
    source_function: str,
    target_type: str,
    target_ids: list,
    payload: Optional[dict] = None,
):
    """Unified audit logging. Call after every write/delete/update operation."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            source_function=source_function,
            target_type=target_type,
            target_ids=target_ids,
            payload=payload or {},
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.warning(f"Audit log write failed (non-fatal): {e}")
        db.rollback()
