"""Bandit state — per-(user, context) LinUCB matrices persisted as JSON blobs."""
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from config import Base


class BanditState(Base):
    __tablename__ = "bandit_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    context_id = Column(String(100), nullable=False)
    A_json = Column(Text, nullable=False, default="[]")
    b_json = Column(Text, nullable=False, default="[]")
    pulled_count = Column(Integer, nullable=False, default=0)
    last_pulled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "context_id", name="uq_user_context"),
    )
