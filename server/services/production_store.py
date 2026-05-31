"""Production rule store — CRUD for compiled expert rules.

Reuses ContextObject table with type="rule", differentiated by tags.
"""
from __future__ import annotations
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import and_, or_
from models.context_object import ContextObject
from schemas.production_rule import ProductionRule, RuleStage

logger = logging.getLogger(__name__)


def _parse_tags(raw_tags):
    """Parse tags that may be a JSON string, list, or None."""
    if raw_tags is None:
        return []
    if isinstance(raw_tags, list):
        return raw_tags
    if isinstance(raw_tags, str):
        import json
        try:
            return json.loads(raw_tags)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _rule_from_obj(obj: ContextObject) -> ProductionRule:
    """Convert a ContextObject to a ProductionRule."""
    tags = _parse_tags(obj.tags)
    return ProductionRule(
        id=obj.id,
        user_id=obj.user_id,
        project_id=None,
        domain=next((t.replace("domain:", "") for t in tags if t.startswith("domain:")), ""),
        title=obj.title,
        trigger=obj.summary or "",
        condition=tags_to_condition(tags),
        action=obj.body or "",
        stage=RuleStage(tags_to_stage(tags)),
        occurrence_count=tags_to_count(tags, "occ:"),
        counter_example_count=tags_to_count(tags, "counter:"),
        confidence=float(obj.confidence) / 5.0 if obj.confidence else 0.1,
        source=obj.source or "compiled",
        tags=tags,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        last_seen_at=obj.last_used_at,
    )


def tags_to_stage(tags: List[str]) -> str:
    for t in tags:
        if t.startswith("stage:"):
            stage_name = t.split(":", 1)[1]
            if stage_name in RuleStage._value2member_map_:
                return stage_name
    return "raw"


def tags_to_condition(tags: List[str]) -> str:
    conditions = [t.split(":", 1)[1] for t in tags if t.startswith("condition:")]
    return "; ".join(conditions) if conditions else ""


def tags_to_count(tags: List[str], prefix: str) -> int:
    for t in tags:
        if t.startswith(prefix):
            try:
                return int(t.split(":", 1)[1])
            except (ValueError, IndexError):
                return 0
    return 0


def create_rule(
    db: DBSession,
    user_id: int,
    trigger: str,
    action: str,
    domain: str = "",
    title: str = "",
    confidence: float = 0.5,
    source: str = "compiled",
    stage: str = "raw",
) -> ProductionRule:
    """Create a new production rule as a ContextObject."""
    tags = [f"stage:{stage}", f"domain:{domain}", "production_rule"]
    rule_id = str(uuid.uuid4())
    obj = ContextObject(
        id=rule_id,
        user_id=user_id,
        type="rule",
        title=title or f"[{domain}] {trigger} → {action}",
        summary=trigger,
        body=action,
        tags=tags,
        source=source,
        status="active",
        confidence=int(confidence * 5),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.info(f"Created production rule: {rule_id} — {trigger} → {action}")
    return _rule_from_obj(obj)


def list_rules(
    db: DBSession,
    user_id: int,
    domain: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = 50,
) -> List[ProductionRule]:
    """List production rules for a user, optionally filtered."""
    q = db.query(ContextObject).filter(
        ContextObject.user_id.in_([user_id, 0]),  # user_id=0 = global system rules
        ContextObject.type == "rule",
        ContextObject.status.in_(["active", "draft"]),
    )
    results = q.order_by(ContextObject.updated_at.desc()).limit(limit).all()
    rules = [_rule_from_obj(r) for r in results]

    if domain:
        rules = [r for r in rules if r.domain == domain]
    if stage:
        rules = [r for r in rules if r.stage == stage]

    return rules


def match_rules(
    db: DBSession,
    user_id: int,
    trigger_text: str,
    domain: Optional[str] = None,
    min_confidence: float = 0.3,
) -> List[ProductionRule]:
    """Find production rules whose trigger matches the given text.

    Uses RuleMatcher semantic matching (entity + keyword + semantic fusion)
    when domain weights are available, falling back to string overlap.
    """
    q = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.type == "rule",
        ContextObject.status.in_(["active", "draft"]),
        ContextObject.confidence >= int(min_confidence * 5),
    )
    if domain:
        objs = q.all()
        objs = [o for o in objs if f"domain:{domain}" in str(o.tags)]
    else:
        objs = q.all()

    rules = [_rule_from_obj(o) for o in objs]
    if not rules:
        return []

    # Use semantic matcher when available
    if trigger_text and trigger_text.strip():
        try:
            from services.rule_matcher import RuleMatcher
            # Use the first rule's domain for weight selection, or pass None for defaults
            match_domain = domain or (rules[0].domain if rules else None)
            matcher = RuleMatcher(domain=match_domain)
            scored = []
            for rule in rules:
                result = matcher.match_score(trigger_text, rule.trigger or "")
                if result["score"] >= 0.25:
                    scored.append((rule, result["score"]))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [r for r, _ in scored[:20]]
        except Exception:
            pass

    # Fallback: token overlap (word-level, handles partial matches)
    rules.sort(key=lambda r: r.confidence, reverse=True)
    matched = []
    trigger_words = set(
        w for w in trigger_text.lower().replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
        if len(w) > 2
    )
    for rule in rules:
        rule_words = set(
            w for w in (rule.trigger or "").lower().replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
            if len(w) > 2
        )
        if not trigger_words or not rule_words:
            continue
        intersection = trigger_words & rule_words
        overlap_ratio = len(intersection) / min(len(trigger_words), len(rule_words))
        if overlap_ratio >= 0.3:
            matched.append(rule)
    return matched[:20]

    return matched[:20]


def update_confidence(
    db: DBSession,
    rule_id: str,
    delta: float,
) -> Optional[ProductionRule]:
    """Increment usage count and recalculate confidence via compute_confidence formula.

    delta > 0: positive reinforcement (rule was useful)
    delta < 0: counter-example (rule was wrong)
    """
    from services.rule_promotion import compute_confidence

    obj = db.query(ContextObject).filter(ContextObject.id == rule_id).first()
    if not obj:
        return None

    tags = obj.tags if isinstance(obj.tags, list) else []
    occ = tags_to_count(tags, "occ:") + 1
    counter = tags_to_count(tags, "counter:")
    if delta < 0:
        counter += 1

    # Determine new stage from counts
    new_stage = _determine_stage(occ, counter)

    # Compute days since last seen
    days_idle = 0
    if obj.last_used_at:
        delta_t = datetime.now(timezone.utc) - obj.last_used_at.replace(tzinfo=timezone.utc)
        days_idle = delta_t.days

    # Use the unified confidence formula
    new_conf_float = compute_confidence(new_stage, occ, counter, days_idle)
    obj.confidence = int(new_conf_float * 5)
    obj.updated_at = datetime.now(timezone.utc)
    obj.last_used_at = datetime.now(timezone.utc)

    tags = [t for t in tags if not t.startswith("occ:") and not t.startswith("stage:") and not t.startswith("counter:")]
    tags.append(f"occ:{occ}")
    if counter > 0:
        tags.append(f"counter:{counter}")
    tags.append(f"stage:{new_stage}")
    obj.tags = tags

    db.commit()
    db.refresh(obj)
    logger.info(
        f"Rule {rule_id}: stage={new_stage}, conf={new_conf_float:.3f} "
        f"(occ={occ}, counter={counter}, idle={days_idle}d)"
    )
    return _rule_from_obj(obj)


def increment_counter(
    db: DBSession,
    rule_id: str,
) -> Optional[ProductionRule]:
    """Record a counter-example for a rule, decreasing its confidence via formula."""
    return update_confidence(db, rule_id, -0.1)


def compile_from_cpg(
    db: DBSession,
    user_id: int,
    decision_graph,  # DecisionGraph
    domain: str,
) -> List[ProductionRule]:
    """Compile a DecisionGraph into production rules and store them."""
    created = []
    for node in decision_graph.nodes:
        if not node.action:
            continue
        rule = create_rule(
            db=db,
            user_id=user_id,
            trigger=node.trigger,
            action=node.action,
            domain=domain,
            title=f"[{domain}] {node.trigger} → {node.action}",
            confidence=0.1,
            source="document",
            stage="raw",
        )
        created.append(rule)
    logger.info(f"Compiled {len(created)} rules from CPG for domain={domain}")
    return created


def _determine_stage(occ: int, counter: int) -> str:
    """Determine rule stage from occurrence and counter counts."""
    if occ >= 10 and counter < 1:
        return "production"
    if occ >= 5 and counter < 1:
        return "stable"
    if occ >= 3 and counter < 2:
        return "repeated"
    if occ >= 2:
        return "candidate"
    return "raw"


# ═══════════════════════════════════════════════════════════
# CBR 4R Cycle (Layer 3)
# Aamodt & Plaza (1994): Case-Based Reasoning
#   Retrieve → Reuse → Revise → Retain
# ═══════════════════════════════════════════════════════════

def run_4r_cycle(
    db: DBSession,
    user_id: int,
    query: str,
    domain: str,
    matched_rules: List[ProductionRule],
    outcome_feedback: Optional[dict] = None,
) -> dict:
    """Execute one full CBR 4R cycle.

    1. Retrieve: find similar past cases in context_objects
    2. Reuse: adapt best-matching case's rules to current query
    3. Revise: update rule confidence from outcome feedback
    4. Retain: store current case for future retrieval

    Args:
        db: database session
        user_id: authenticated user
        query: the current user query / case description
        domain: domain identifier
        matched_rules: rules that matched the current query
        outcome_feedback: optional {rule_id: was_correct (bool)} from user/expert

    Returns dict with trace of each R step.
    """
    from datetime import datetime, timezone
    import json as _json
    from models.context_object import ContextObject

    # Convert dict rules to objects if needed (inference engine returns dicts)
    class _RuleObj:
        def __init__(self, d):
            self.id = d.get('id','') if isinstance(d, dict) else getattr(d, 'id', '')
            self.domain = d.get('domain','') if isinstance(d, dict) else getattr(d, 'domain', '')
            self.trigger = d.get('trigger','') if isinstance(d, dict) else getattr(d, 'trigger', '')
            self.action = d.get('action','') if isinstance(d, dict) else getattr(d, 'action', '')
            self.confidence = d.get('confidence',0) if isinstance(d, dict) else getattr(d, 'confidence', 0)
    matched_rules = [_RuleObj(r) for r in matched_rules]

    trace = []

    # ── 1. RETRIEVE: find similar past cases ──
    similar_cases = []
    try:
        # Search existing cases in same domain
        past_cases = db.query(ContextObject).filter(
            ContextObject.user_id == user_id,
            ContextObject.type == "rule",
            ContextObject.status == "active",
        ).order_by(ContextObject.updated_at.desc()).limit(30).all()

        # Rank by trigger text overlap with current query
        query_lower = query.lower()
        scored_cases = []
        for pc in past_cases:
            trigger = (pc.summary or "").lower()
            if not trigger:
                continue
            overlap = sum(1 for w in query_lower.split() if w in trigger)
            if overlap > 0:
                scored_cases.append((pc, overlap))
        scored_cases.sort(key=lambda x: x[1], reverse=True)
        similar_cases = scored_cases[:5]
        trace.append(f"Retrieve: found {len(similar_cases)} similar past cases")
    except Exception as e:
        trace.append(f"Retrieve: skipped ({e})")

    # ── 2. REUSE: adapt best case's rules ──
    reused_rule_ids = []
    if similar_cases and matched_rules:
        best_case, _ = similar_cases[0]
        best_tags = best_case.tags if isinstance(best_case.tags, list) else []
        # If the past case had confirmed rules, boost current matches
        for rule in matched_rules:
            r_domain = rule.domain if hasattr(rule, 'domain') else rule.get('domain','')
            r_id = rule.id if hasattr(rule, 'id') else rule.get('id','')
            if r_domain == domain:
                reused_rule_ids.append(r_id)
        trace.append(f"Reuse: adapted {len(reused_rule_ids)} rules from past case")
    else:
        trace.append("Reuse: no past cases to adapt — using current rules as-is")
        reused_rule_ids = [r.id for r in matched_rules]

    # ── 3. REVISE: update confidence from outcome feedback ──
    revised_count = 0
    if outcome_feedback:
        for rule_id, was_correct in outcome_feedback.items():
            delta = 0.1 if was_correct else -0.1
            update_confidence(db, rule_id, delta)
            revised_count += 1
        trace.append(f"Revise: updated confidence for {revised_count} rules")
    else:
        # Default: mark as used (slight positive reinforcement)
        for rule in matched_rules[:5]:
            if rule.id:
                increment_counter(db, rule.id)
        trace.append("Revise: no explicit feedback — incremented usage counters")

    # ── 4. RETAIN: store current case ──
    try:
        case_id = str(__import__('uuid').uuid4())
        now = datetime.now(timezone.utc)
        rule_summary = "; ".join(
            f"{r.trigger[:50]}→{r.action[:30]}" for r in matched_rules[:3]
        )
        case_obj = ContextObject(
            id=case_id,
            user_id=user_id,
            type="rule",
            title=f"Case: {query[:80]}",
            summary=query[:200],
            body="; ".join(
                f"{r.trigger[:50]}->{r.action[:30]}" for r in matched_rules[:3]
            )[:500],
            tags=[f"domain:{domain}", "4r_case", "stage:raw"],
            source="manual",
            status="active",
            confidence=1,
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )
        db.add(case_obj)
        db.commit()
        trace.append(f"Retain: stored case {case_id} for future retrieval")
    except Exception as e:
        trace.append(f"Retain: skipped ({e})")

    return {
        "cycle": "4R",
        "retrieved_cases": len(similar_cases),
        "reused_rules": len(reused_rule_ids),
        "revised_rules": revised_count,
        "retained": True,
        "trace": trace,
    }
