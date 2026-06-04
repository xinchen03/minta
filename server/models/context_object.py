"""SQLAlchemy model for context_objects table."""
import json
from sqlalchemy import Column, String, Text, Integer, Enum as SAEnum, DateTime, JSON
from sqlalchemy.sql import func
from config import Base


class ContextObject(Base):
    __tablename__ = "context_objects"

    id = Column(String(100), primary_key=True)
    user_id = Column(Integer, nullable=True)
    type = Column(
        SAEnum(
            "preference", "workflow", "project_context", "decision_criteria",
            "lesson_learned", "writing_style", "rule", "ai_brief", "work_profile",
            "task_note",
            name="context_object_type",
        ),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    summary = Column(String(500), default="")
    body = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    source = Column(
        SAEnum("manual", "conversation", "document", "counter_example", "skill", name="context_source"),
        default="manual",
    )
    status = Column(
        SAEnum("draft", "active", "stale", "archived", name="context_status"),
        default="active",
    )
    confidence = Column(Integer, default=3)
    cover_image = Column(String(500), nullable=True)
    is_public = Column(Integer, default=0)
    owner_name = Column(String(50), nullable=True)
    embedding_384 = Column(Text, nullable=True)   # JSON float array, sentence-transformers output
    pca_embedding_32 = Column(Text, nullable=True) # JSON float array, 32d PCA reduced
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    archived_reason = Column(String(50), nullable=True)

    def _parse_tags(self):
        t = self.tags
        if t is None:
            return []
        if isinstance(t, str):
            try:
                return json.loads(t)
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(t, list):
            return t
        return []

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "summary": self.summary or "",
            "body": self.body or "",
            "tags": self._parse_tags(),
            "source": self.source,
            "status": self.status,
            "confidence": self.confidence,
            "coverImage": self.cover_image or None,
            "isPublic": bool(self.is_public) if self.is_public is not None else False,
            "ownerName": self.owner_name or None,
            "createdAt": str(self.created_at) if self.created_at else "",
            "updatedAt": str(self.updated_at) if self.updated_at else "",
            "lastUsedAt": str(self.last_used_at) if self.last_used_at else None,
        }
