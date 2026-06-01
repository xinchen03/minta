"""User activity log — lightweight engagement tracking for thesis analysis."""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from config import Base


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)   # login, context_view, brief_generate, brief_copy, inbox_archive, skill_share, settings_view
    detail = Column(String(200), nullable=True)        # optional context (e.g., "3 cards selected")
    created_at = Column(DateTime, server_default=func.now())
