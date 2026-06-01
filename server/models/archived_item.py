"""SQLAlchemy model for archived_items table."""
from sqlalchemy import Column, String, Text, Integer, Float, DateTime
from sqlalchemy.sql import func
from config import Base


class ArchivedItem(Base):
    __tablename__ = "archived_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    slot_label = Column(String(64), nullable=False)
    content = Column(Text, nullable=False)
    retention_score = Column(Float, nullable=False)
    archived_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "slotLabel": self.slot_label,
            "content": self.content or "",
            "retentionScore": self.retention_score,
            "archivedAt": str(self.archived_at) if self.archived_at else "",
        }
