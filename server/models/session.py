"""SQLAlchemy model for sessions table."""
from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.sql import func
from config import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=False)
    project_path = Column(String(512), nullable=True)
    observation_count = Column(Integer, default=0)
    correction_count = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "projectPath": self.project_path,
            "observationCount": self.observation_count or 0,
            "correctionCount": self.correction_count or 0,
            "summary": self.summary or "",
            "createdAt": str(self.created_at) if self.created_at else "",
            "endedAt": str(self.ended_at) if self.ended_at else None,
        }
