"""Inference log — JEPA temporal state sequence.

Stores every inference interaction with full context for:
- JEPA temporal state prediction training
- L3 CBR 4R case retrieval
- Audit trail and version tracking
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from config import Base


class InferenceLog(Base):
    __tablename__ = "inference_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)

    # Current state
    user_message = Column(Text, nullable=False)
    user_message_emb = Column(JSON, nullable=True)       # 384d embedding
    abstract_action = Column(String(100), nullable=True)  # BehaviorAbstraction output
    matched_rules = Column(JSON, nullable=True)           # [{trigger, action, confidence}]
    confidence = Column(Float, nullable=True)
    mode = Column(String(10), nullable=True)              # s1 / s2
    suggested_step = Column(Text, nullable=True)
    missing_info = Column(JSON, nullable=True)

    # JEPA temporal metadata
    session_seq_id = Column(Integer, nullable=True)       # position in session
    prev_state_emb = Column(JSON, nullable=True)           # previous interaction's embedding
    jepa_predicted_emb = Column(JSON, nullable=True)       # JEPA predicted embedding
    state_similarity = Column(Float, nullable=True)         # A vs B similarity
    audit_verdict = Column(String(10), nullable=True)       # pass / flag / reject

    # Version tracking
    rule_ids = Column(JSON, nullable=True)                  # [rule_id, ...]
    predictor_version = Column(String(20), nullable=True)

    # Feedback
    user_signal = Column(String(10), nullable=True)         # positive / negative / neutral
    feedback_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
