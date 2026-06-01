"""SQLAlchemy model for inbox_items table."""
import json
from sqlalchemy import Column, Integer, String, Text, Float, Enum as SAEnum, DateTime, JSON
from sqlalchemy.sql import func
from config import Base


class InboxItem(Base):
    __tablename__ = "inbox_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    type = Column(String(50), nullable=True)  # suggested/assigned ContextObject type
    confidence = Column(Float, default=0.7)
    status = Column(
        SAEnum("pending", "archived", "discarded", name="inbox_status"),
        default="pending",
    )
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())

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
            "text": self.text,
            "type": self.type,
            "confidence": self.confidence,
            "status": self.status,
            "tags": self._parse_tags(),
            "createdAt": str(self.created_at) if self.created_at else None,
        }
