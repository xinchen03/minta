"""Rule Promotion Pipeline — 5-stage promotion from raw decision graphs to stable productions.

Stages: Raw → Candidate (>=2 occ) → Repeated (>=3 + user confirm)
       → Stable (>=5 + counter<1) → Production (>=10 + sustained stability)

Integrates with Minta's existing mechanisms:
- DecayService: low-frequency rules lose confidence over time
- ConflictService: detect contradictory rules
- RedundancyService: merge similar rules
- FragmentService: assemble scattered DecisionGraph fragments
"""
from __future__ import annotations
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session as DBSession
from models.context_object import ContextObject
from schemas.production_rule import (
    RuleStage, PromotionReport, ConflictReport, ProductionRule,
    STAGE_BASE_CONFIDENCE, STAGE_OCCURRENCE_THRESHOLD,
)
from services.production_store import (
    _rule_from_obj, list_rules as list_production_rules,
    update_confidence,
)

logger = logging.getLogger(__name__)


def compute_confidence(
    stage: RuleStage,
    occurrence_count: int,
    counter_example_count: int,
    days_since_last_seen: int = 0,
) -> float:
    """Compute rule confidence from stage, usage counts, counter examples, and recency.

    Formula (from Minta Expert roadmap):
      base = STAGE_BASE_CONFIDENCE[stage]  (0.1, 0.25, 0.4, 0.7, 0.9)
      penalty = counter_example_count * 0.1
      if days_since_last_seen > 30:
          time_decay = min(1.0, (days_since_last_seen - 30) / 60)
          base -= time_decay * base
      return max(0.0, min(1.0, base - penalty))

    Returns float 0.0–1.0.
    """
    if isinstance(stage, str):
        stage = RuleStage(stage)
    base = STAGE_BASE_CONFIDENCE[stage]
    penalty = counter_example_count * 0.1

    if days_since_last_seen > 30:
        time_decay = min(1.0, (days_since_last_seen - 30) / 60.0)
        base -= time_decay * base

    return max(0.0, min(1.0, base - penalty))


class RulePromotionPipeline:
    """Five-stage promotion pipeline for procedural knowledge."""

    def __init__(self, db: DBSession):
        self.db = db

    # ── Promotion Logic ──

    def promote(self, rule: ProductionRule, occurrence_count: int,
                counter_count: int, user_confirmed: bool = False) -> RuleStage:
        """Determine new stage based on counts and user confirmation."""
        new_stage = self._classify(occurrence_count, counter_count, user_confirmed)
        current = RuleStage(rule.stage) if isinstance(rule.stage, str) else rule.stage

        if new_stage == current:
            return current

        # Prevent skipping stages (except on promotion)
        stages = list(RuleStage)
        current_idx = stages.index(current)
        new_idx = stages.index(new_stage)
        if new_idx > current_idx + 1:
            # Only promote one level at a time
            return stages[current_idx + 1]
        if new_idx < current_idx:
            # Allow demotion by only one level
            return stages[max(0, current_idx - 1)]

        return new_stage

    def _classify(self, occ: int, counter: int, user_confirmed: bool) -> RuleStage:
        if occ >= 10 and counter < 1:
            return RuleStage.PRODUCTION
        if occ >= 5 and counter < 1:
            return RuleStage.STABLE
        if occ >= 3 and (counter < 2 or user_confirmed):
            return RuleStage.REPEATED
        if occ >= 2:
            return RuleStage.CANDIDATE
        return RuleStage.RAW

    # ── Decay ──

    def apply_decay(self, rule_id: str, days_since_last_seen: Optional[int] = None) -> Optional[ProductionRule]:
        """Recalculate confidence with time decay via compute_confidence formula."""
        obj = self.db.query(ContextObject).filter(ContextObject.id == rule_id).first()
        if not obj:
            return None

        if days_since_last_seen is None:
            if obj.last_used_at:
                delta = datetime.now(timezone.utc) - obj.last_used_at.replace(tzinfo=timezone.utc)
                days_since_last_seen = delta.days
            else:
                days_since_last_seen = 0

        tags = obj.tags if isinstance(obj.tags, list) else []
        current_stage = next((t.split(":", 1)[1] for t in tags if t.startswith("stage:")), "raw")
        occ = int(next((t.split(":", 1)[1] for t in tags if t.startswith("occ:")), "0"))
        counter = int(next((t.split(":", 1)[1] for t in tags if t.startswith("counter:")), "0"))

        new_conf = compute_confidence(current_stage, occ, counter, days_since_last_seen)
        obj.confidence = int(new_conf * 5)

        if days_since_last_seen > 30 and occ < STAGE_OCCURRENCE_THRESHOLD.get(RuleStage(current_stage), 0):
            lower_stage = self._demote_stage(current_stage)
            tags = [t for t in tags if not t.startswith("stage:")]
            tags.append(f"stage:{lower_stage}")
            obj.tags = tags

        obj.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info(
            f"Decay applied to rule {rule_id}: conf={new_conf:.3f} "
            f"(stage={current_stage}, occ={occ}, counter={counter}, idle={days_since_last_seen}d)"
        )
        return _rule_from_obj(obj)

    def _demote_stage(self, stage: str) -> str:
        stages = ["raw", "candidate", "repeated", "stable", "production"]
        if stage in stages:
            idx = stages.index(stage)
            return stages[max(0, idx - 1)]
        return "raw"

    # ── Conflict Detection ──

    def detect_conflicts(self, rule_a_id: str, rule_b_id: str) -> ConflictReport:
        """Detect if two rules contradict each other."""
        a = self.db.query(ContextObject).filter(ContextObject.id == rule_a_id).first()
        b = self.db.query(ContextObject).filter(ContextObject.id == rule_b_id).first()
        if not a or not b:
            return ConflictReport(rule_a_id=rule_a_id, rule_b_id=rule_b_id,
                                  description="One or both rules not found")

        a_action = (a.body or "").strip()
        b_action = (b.body or "").strip()
        a_trigger = (a.summary or "").strip()
        b_trigger = (b.summary or "").strip()

        report = ConflictReport(rule_a_id=rule_a_id, rule_b_id=rule_b_id)

        # Same trigger, different actions → contradictory
        if a_trigger.lower() == b_trigger.lower() and a_action.lower() != b_action.lower():
            report.conflict_type = "contradictory_action"
            report.description = f"Same trigger '{a_trigger}' yields different actions: '{a_action}' vs '{b_action}'"
            report.resolution_suggestion = "Lower confidence of the rule with fewer occurrences"
            return report

        # Similar triggers, same action → redundant
        trigger_overlap = self._text_overlap(a_trigger, b_trigger)
        action_overlap = self._text_overlap(a_action, b_action)
        if trigger_overlap > 0.7 and action_overlap > 0.7:
            report.conflict_type = "redundant"
            report.description = f"Highly similar rules (trigger sim={trigger_overlap:.2f}, action sim={action_overlap:.2f})"
            report.resolution_suggestion = "Merge into single rule, keep the one with higher confidence"
            return report

        if trigger_overlap > 0.5 and action_overlap < 0.3:
            report.conflict_type = "overlapping"
            report.description = f"Similar triggers but different actions (trigger sim={trigger_overlap:.2f})"
            report.resolution_suggestion = "Keep both, add clarifying conditions to differentiate"

        return report

    def _text_overlap(self, a: str, b: str) -> float:
        from difflib import SequenceMatcher
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    # ── Redundancy Compression ──

    def merge_redundant(self, rule_a_id: str, rule_b_id: str) -> Optional[ProductionRule]:
        """Merge two redundant rules, keeping the one with higher confidence."""
        a = self.db.query(ContextObject).filter(ContextObject.id == rule_a_id).first()
        b = self.db.query(ContextObject).filter(ContextObject.id == rule_b_id).first()
        if not a or not b:
            return None

        a_conf = a.confidence or 0
        b_conf = b.confidence or 0

        if a_conf >= b_conf:
            keeper, goner = a, b
        else:
            keeper, goner = b, a

        # Merge tags
        k_tags = keeper.tags if isinstance(keeper.tags, list) else []
        g_tags = goner.tags if isinstance(goner.tags, list) else []
        merged_tags = list(set(k_tags + g_tags))
        keeper.tags = merged_tags

        # Sum occurrences
        occ_a = int(next((t.split(":",1)[1] for t in k_tags if t.startswith("occ:")), "0"))
        occ_b = int(next((t.split(":",1)[1] for t in g_tags if t.startswith("occ:")), "0"))
        merged_tags = [t for t in merged_tags if not t.startswith("occ:")]
        merged_tags.append(f"occ:{occ_a + occ_b}")
        keeper.tags = merged_tags

        # Archive the goner
        goner.status = "archived"
        goner.updated_at = datetime.now(timezone.utc)
        keeper.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        logger.info(f"Merged rules: {rule_b_id} → {rule_a_id} (keeper conf={keeper.confidence})")
        return _rule_from_obj(keeper)

    # ── Fragment Assembly ──

    def assemble_fragments(self, fragment_ids: List[str]) -> Optional[ProductionRule]:
        """Assemble scattered DecisionGraph fragments into a complete rule."""
        fragments = self.db.query(ContextObject).filter(
            ContextObject.id.in_(fragment_ids),
            ContextObject.type == "rule",
        ).all()
        if len(fragments) < 2:
            return None

        # Combine triggers and actions
        triggers = [f.summary for f in fragments if f.summary]
        actions = [f.body for f in fragments if f.body]
        all_tags = []
        max_occ = 0
        for f in fragments:
            tags = f.tags if isinstance(f.tags, list) else []
            all_tags.extend(tags)
            occ = int(next((t.split(":",1)[1] for t in tags if t.startswith("occ:")), "0"))
            max_occ = max(max_occ, occ)

        merged_tags = list(set(all_tags))
        merged_tags = [t for t in merged_tags if not t.startswith("occ:")]
        merged_tags.append(f"occ:{max_occ}")

        # Update first fragment, archive rest
        keeper = fragments[0]
        keeper.summary = "; ".join(triggers)
        keeper.body = "; ".join(actions)
        keeper.tags = merged_tags
        keeper.updated_at = datetime.now(timezone.utc)

        for f in fragments[1:]:
            f.status = "archived"
            f.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        logger.info(f"Assembled {len(fragments)} fragments into rule {keeper.id}")
        return _rule_from_obj(keeper)

    # ── Main Cycle ──

    def run_cycle(self, user_id: int, domain: Optional[str] = None) -> PromotionReport:
        """Run one full promotion cycle for a user's rules."""
        cycle_id = str(uuid.uuid4())[:8]
        report = PromotionReport(cycle_id=cycle_id)

        try:
            rules = list_production_rules(self.db, user_id, domain=domain, limit=200)

            for rule in rules:
                # 1. Check decay
                self.apply_decay(rule.id, days_since_last_seen=None)

                # 2. Check promotion/demotion
                new_stage = self.promote(
                    rule, rule.occurrence_count,
                    rule.counter_example_count, user_confirmed=False,
                )
                if new_stage.value != rule.stage:
                    stages_rank = {"raw": 0, "candidate": 1, "repeated": 2, "stable": 3, "production": 4}
                    if stages_rank.get(new_stage.value, 0) > stages_rank.get(rule.stage, 0):
                        report.rules_promoted += 1
                    else:
                        report.rules_demoted += 1

                    obj = self.db.query(ContextObject).filter(ContextObject.id == rule.id).first()
                    if obj:
                        tags = obj.tags if isinstance(obj.tags, list) else []
                        tags = [t for t in tags if not t.startswith("stage:")]
                        tags.append(f"stage:{new_stage.value}")
                        obj.tags = tags
                        obj.updated_at = datetime.now(timezone.utc)
                        report.details.append(
                            f"Rule {rule.title[:40]}: {rule.stage} → {new_stage.value}"
                        )

            self.db.commit()

        except Exception as e:
            logger.error(f"Promotion cycle {cycle_id} failed: {e}")
            report.details.append(f"Error: {e}")

        logger.info(
            f"Promotion cycle {cycle_id}: promoted={report.rules_promoted}, "
            f"demoted={report.rules_demoted}, merged={report.rules_merged}, "
            f"decayed={report.rules_decayed}"
        )
        return report
