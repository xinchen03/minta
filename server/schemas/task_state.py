"""Task State schemas — working memory (Layer 0) for active reasoning sessions."""
from __future__ import annotations
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Hypothesis(BaseModel):
    """A hypothesis under consideration during reasoning."""
    id: str
    description: str
    confidence: float = 0.5
    evidence: List[str] = []
    status: str = "active"                # active | confirmed | rejected


class DecisionStep(BaseModel):
    """A single step in the decision stack."""
    step: str
    result: str = ""
    rule_id: Optional[str] = None         # which rule was activated
    timestamp: datetime = Field(default_factory=datetime.now)


class TaskState(BaseModel):
    """Current working memory state for a session."""
    session_id: str
    user_id: Optional[int] = None
    active_task: str = ""
    domain: str = ""                      # e.g. "ankle_injury"
    active_hypotheses: List[Hypothesis] = []
    rejected_hypotheses: List[Hypothesis] = []
    confirmed_hypotheses: List[Hypothesis] = []
    pending_questions: List[str] = []
    current_step: Optional[str] = None
    decision_stack: List[DecisionStep] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class InferenceResult(BaseModel):
    """Result from inference engine."""
    activated_rules: list = []
    suggested_next_step: Optional[str] = None
    missing_info: List[str] = []
    analogous_cases: list = []
    task_state_update: Optional[dict] = None
    confidence: float = 0.0
    mode: str = "s2"                      # s1 (fast) or s2 (slow / gap detection)
    reasoning_trace: List[str] = []
