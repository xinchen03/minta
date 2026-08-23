"""Decay Engine — exponential retention scoring with type-specific stability constants.

Implements Eq.2 from the Minta paper:
    R_i(t) = r_i^0 * exp(-Δt_i / S_type)

Where S_type is the type-specific stability (1/e decay time constant, days).
The time to halve is S_type * ln(2) ≈ 0.693 * S_type.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Type-specific stability constants (days to 1/e) — from calibration study
# S_type values: higher = slower decay (more stable)
S_TYPE: Dict[str, float] = {
    "preference": 152,
    "personal_fact": 102,
    "project_state": 120,
    "project_context": 120,
    "emotion": 100,
    "task_note": 113,
    "workflow": 113,
    "decision_criteria": 120,
    "lesson_learned": 152,
    "writing_style": 152,
    "work_profile": 152,
    "ai_brief": 100,
    "rule": 200,
}
DEFAULT_S = 113.0

THETA_S = 0.3


def get_stability(context_type: str) -> float:
    """Get type-specific stability constant S_type (1/e decay point in days)."""
    return S_TYPE.get(context_type, DEFAULT_S)


# Backward-compat alias — keep existing callers working
get_half_life = get_stability


def compute_retention(
    *,
    initial_relevance: float,
    last_access: datetime,
    context_type: str,
    now: Optional[datetime] = None,
) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    if last_access.tzinfo is None:
        last_access = last_access.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta_days = (now - last_access).total_seconds() / 86400.0
    if delta_days < 0:
        delta_days = 0.0

    stability = get_stability(context_type)
    retention = initial_relevance * math.exp(-delta_days / stability)
    return round(retention, 6)


def classify_staleness(
    *,
    initial_relevance: float,
    last_access: datetime,
    context_type: str,
    now: Optional[datetime] = None,
) -> str:
    if initial_relevance < THETA_S:
        return "archived"
    r = compute_retention(
        initial_relevance=initial_relevance,
        last_access=last_access,
        context_type=context_type,
        now=now,
    )
    return "active" if r >= THETA_S else "stale"


def initial_relevance_from_confidence(confidence: int) -> float:
    return max(0.0, min(1.0, confidence / 5.0))


# ── MemStrata-style bi-temporal validity (2026 integration) ──

def check_temporal_validity(
    *,
    valid_from: Optional[datetime] = None,
    valid_to: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    superseded_by: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Check bi-temporal validity before falling back to decay.

    Returns:
        {"status": "active"|"stale"|"superseded"|"expired"|"defer_to_decay",
         "reason": str}
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Foresight expiry (EverMemOS-style): temporary states
    if valid_until is not None:
        if valid_until.tzinfo is None:
            valid_until_aware = valid_until.replace(tzinfo=timezone.utc)
        else:
            valid_until_aware = valid_until
        if now > valid_until_aware:
            return {"status": "expired", "reason": f"valid_until passed: {valid_until}"}

    # 2. Bi-temporal supersession (MemStrata-style)
    if superseded_by is not None and superseded_by.strip():
        return {"status": "superseded", "reason": f"superseded_by: {superseded_by}"}

    # 3. Bi-temporal window (MemStrata-style)
    if valid_from is not None or valid_to is not None:
        if valid_from is not None:
            vf = valid_from.replace(tzinfo=timezone.utc) if valid_from.tzinfo is None else valid_from
            if now < vf:
                return {"status": "stale", "reason": f"not yet valid (from {valid_from})"}
        if valid_to is not None:
            vt = valid_to.replace(tzinfo=timezone.utc) if valid_to.tzinfo is None else valid_to
            if now > vt:
                return {"status": "stale", "reason": f"validity window expired (to {valid_to})"}

    # 4. No bi-temporal constraints → defer to exponential decay
    return {"status": "defer_to_decay", "reason": "no bi-temporal constraints set"}


def classify_staleness_with_bitemporal(
    *,
    initial_relevance: float,
    last_access: datetime,
    context_type: str,
    valid_from: Optional[datetime] = None,
    valid_to: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    superseded_by: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Classify staleness with bi-temporal checks before exponential decay.

    Priority: valid_until expiry > superseded_by > bi-temporal window > exponential decay.
    """
    tv = check_temporal_validity(
        valid_from=valid_from, valid_to=valid_to,
        valid_until=valid_until, superseded_by=superseded_by,
        now=now,
    )
    if tv["status"] != "defer_to_decay":
        if tv["status"] == "expired":
            return "stale"
        if tv["status"] == "superseded":
            return "stale"
        if tv["status"] == "stale":
            return "stale"

    # Fall back to original exponential decay
    return classify_staleness(
        initial_relevance=initial_relevance,
        last_access=last_access,
        context_type=context_type,
        now=now,
    )
