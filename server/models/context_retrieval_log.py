"""Retrieval log — records every context selection for offline IPS evaluation."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.sql import func
from config import Base


class ContextRetrievalLog(Base):
    __tablename__ = "context_retrieval_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(50), nullable=False)
    task_embedding = Column(Text, nullable=True)          # JSON array (32d PCA)
    ranked_context_ids = Column(Text, nullable=False)      # JSON array of IDs
    scores = Column(Text, nullable=False)                  # JSON array of scores
    k_shown = Column(Integer, nullable=False, default=3)
    exp_condition = Column("exp_condition", String(20), nullable=False)
    context_count = Column(Integer, nullable=False, default=0)
    policy = Column(String(20), nullable=False, default="bm25")  # "bm25" | "pcl_bandit"
    created_at = Column(DateTime, server_default=func.now())
