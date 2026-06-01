"""Task reward log — composite reward per task for bandit learning."""
from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from config import Base


class TaskRewardLog(Base):
    __tablename__ = "task_reward_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(50), nullable=False)
    exp_condition = Column("exp_condition", String(20), nullable=False)
    context_count = Column(Integer, nullable=False, default=0)

    # Reward components
    iteration_count = Column(Integer, nullable=False, default=1)
    direct_copy = Column(Integer, nullable=False, default=0)     # 0/1
    quality_rating = Column(Float, nullable=True)                # 1-5 or NULL

    # Composite reward (pre-computed)
    composite_reward = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, server_default=func.now())
