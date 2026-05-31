"""Decay Engine — public-safe version with default parameters.

Calibrated S_TYPE values are in the private Minta-next repo.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Dict, Optional

# Default stability constants (NOT calibrated — safe for public)
S_TYPE: Dict[str, float] = {
    "preference": 150, "personal_fact": 100, "project_state": 120,
    "project_context": 120, "emotion": 100, "task_note": 110,
    "workflow": 110, "decision_criteria": 120, "lesson_learned": 150,
    "writing_style": 150, "work_profile": 150, "ai_brief": 100, "rule": 200,
}
DEFAULT_S = 110.0
THETA_S = 0.30


def get_stability(context_type: str) -> float:
    return S_TYPE.get(context_type, DEFAULT_S)


get_half_life = get_stability


def compute_retention(*, initial_relevance: float, last_access: datetime,
                      context_type: str, now: Optional[datetime] = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    if last_access.tzinfo is None:
        last_access = last_access.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    S = get_stability(context_type)
    delta_days = (now - last_access).total_seconds() / 86400.0
    return round(initial_relevance * math.exp(-delta_days / S), 4)


def initial_relevance_from_confidence(confidence: int) -> float:
    mapping = {1: 0.3, 2: 0.5, 3: 0.7, 4: 0.85, 5: 1.0}
    return mapping.get(confidence, 0.7)
