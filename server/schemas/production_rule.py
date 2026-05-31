"""Production rule schemas — 5-stage promotion pipeline for compiled rules."""
from __future__ import annotations
from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class RuleStage(str, Enum):
    RAW = "raw"                # freshly compiled/extracted
    CANDIDATE = "candidate"    # >= 2 occurrences
    REPEATED = "repeated"      # >= 3 occurrences + user confirmation
    STABLE = "stable"          # >= 5 occurrences + counter < 1
    PRODUCTION = "production"  # >= 10 occurrences + sustained stability


STAGE_BASE_CONFIDENCE = {
    RuleStage.RAW: 0.10,
    RuleStage.CANDIDATE: 0.25,
    RuleStage.REPEATED: 0.40,
    RuleStage.STABLE: 0.70,
    RuleStage.PRODUCTION: 0.90,
}

STAGE_OCCURRENCE_THRESHOLD = {
    RuleStage.RAW: 0,
    RuleStage.CANDIDATE: 2,
    RuleStage.REPEATED: 3,
    RuleStage.STABLE: 5,
    RuleStage.PRODUCTION: 10,
}


class ProductionRule(BaseModel):
    """A compiled production rule stored in ContextObject (type='production_rule')."""
    id: str
    user_id: Optional[int] = None
    project_id: Optional[str] = None
    domain: str = ""
    title: str                            # short description
    trigger: str                          # when this rule fires
    condition: str = ""                   # additional constraints
    action: str                           # what to do
    decision_graph_ref: Optional[str] = None  # link to DecisionGraph if compiled from CPG
    stage: RuleStage = RuleStage.RAW
    occurrence_count: int = 0
    counter_example_count: int = 0
    confidence: float = 0.1
    source: str = "compiled"              # compiled | mined | manual
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class PromotionReport(BaseModel):
    """Report from a promotion cycle run."""
    cycle_id: str
    rules_promoted: int = 0
    rules_demoted: int = 0
    rules_merged: int = 0
    rules_decayed: int = 0
    conflicts_detected: int = 0
    details: List[str] = []


class ConflictReport(BaseModel):
    """Report on a conflict between two rules."""
    rule_a_id: str
    rule_b_id: str
    conflict_type: str = ""               # contradictory_action | redundant | overlapping
    description: str = ""
    resolution_suggestion: str = ""
