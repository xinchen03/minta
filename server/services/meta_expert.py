"""Meta Expert — federated expert system with shared epistemic philosophy.

Architecture:
  ┌─ Meta-Philosophy (epistemic norms, reasoning principles) ─┐
  │  Inherited by ALL domain experts                           │
  ├────────────────────────────────────────────────────────────┤
  │  ┌─ Ankle Expert ─┐  ┌─ Concussion Expert ─┐             │
  │  │ domain rules    │  │ domain rules         │             │
  │  │ + meta rules    │  │ + meta rules         │             │
  │  └────────┬────────┘  └──────────┬───────────┘             │
  │           └── expert.call() ─────┘                         │
  └────────────────────────────────────────────────────────────┘

Each domain expert:
  1. Inherits meta_rules (universal reasoning norms)
  2. Owns domain-specific production rules
  3. Can call other experts for consultation
  4. Shares counter-examples via Behavior Abstraction
"""
from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from collections import defaultdict
from sqlalchemy.orm import Session as DBSession

from schemas.production_rule import ProductionRule, RuleStage
from schemas.task_state import InferenceResult
from services.behavior_abstraction import BehaviorAbstraction
from services.production_store import match_rules as store_match_rules

logger = logging.getLogger(__name__)

ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"


class MetaExpert:
    """Federated expert hub — manages multiple domain experts under shared philosophy."""

    def __init__(self, db: DBSession = None):
        self.db = db
        self._load_philosophy()
        self._experts: Dict[str, Dict] = {}          # domain → expert metadata
        self._cross_domain_links: Dict[str, List[str]] = defaultdict(list)  # op_name → [domain, ...]
        self._behavior = BehaviorAbstraction()
        self._consultation_log: List[Dict] = []
        if db is not None:
            self._auto_discover(db)

    def _auto_discover(self, db) -> None:
        """Auto-register experts from production rules in context_objects.
        Prevents loss on server restart (in-memory reset).
        """
        import json as _json
        from sqlalchemy import text as _sa_text
        try:
            rows = db.execute(
                _sa_text(
                    "SELECT DISTINCT tags FROM context_objects "
                    "WHERE type='rule' AND status='active' AND tags IS NOT NULL"
                )
            ).fetchall()
            domains_found: set = set()
            for row in rows:
                tags = row[0]
                if isinstance(tags, str):
                    try:
                        tags = _json.loads(tags)
                    except Exception:
                        continue
                if isinstance(tags, list):
                    for t in tags:
                        if t.startswith("domain:"):
                            domains_found.add(t.split(":", 1)[1])
            # Restore trust metrics from inference_log (persistent storage)
            trust_map = {}
            try:
                fb_rows = db.execute(
                    _sa_text(
                        "SELECT domain, user_signal, COUNT(*) FROM inference_log "
                        "WHERE user_signal IS NOT NULL GROUP BY domain, user_signal"
                    )
                ).fetchall()
                for row in fb_rows:
                    d, sig, cnt = row[0], row[1], row[2]
                    if d not in trust_map:
                        trust_map[d] = {"pos": 0, "neg": 0}
                    trust_map[d]["pos" if sig == "positive" else "neg"] += cnt
            except Exception:
                pass

            for domain in domains_found:
                td = trust_map.get(domain, {})
                total = td.get("pos", 0) + td.get("neg", 0)
                track = round(td.get("pos", 0) / total, 3) if total > 0 else 0.0

                if domain not in self._experts:
                    self._experts[domain] = {
                        "title": domain.replace("_", " ").title(),
                        "description": "Auto-discovered from production rules",
                        "cpg_source": "", "source_quality": "clinical_practice_guideline",
                        "agent_type": "contributory",
                        "rule_count": 0, "inference_count": total,
                        "track_record": track, "dialectical_performance": 0.0,
                        "peer_agreement": 0.0, "status": "active",
                        "falsification_history": [], "cross_domain_links": {},
                        "skill_references": [],
                    }
                    logger.info(f"Auto-registered expert: {domain} (trust={track:.0%})")
        except Exception as e:
            logger.warning(f"Auto-discover experts failed: {e}")

    def _load_philosophy(self):
        path = ONTOLOGY_DIR / "meta_philosophy.json"
        with open(path, "r", encoding="utf-8") as f:
            self.philosophy = json.load(f)

    # ── Domain Expert Lifecycle ──

    def register_expert(
        self,
        domain: str,
        title: str,
        description: str = "",
        cpg_source: str = "",
        source_quality: str = "clinical_practice_guideline",
        parent_domain: Optional[str] = None,
        agent_type: str = "contributory",
    ) -> Dict:
        """Register a new domain expert in the federation.

        Args:
            domain: unique domain identifier (e.g. 'ankle_injury')
            title: human-readable name
            description: what this expert covers
            cpg_source: DOI or citation of the source CPG
            source_quality: evidence level
            parent_domain: optional parent domain
            agent_type: 'contributory' (can make domain judgments) or
                       'interactional' (can translate between domains)

        Collins & Evans (2007):
          Contributory = can DO the practice (has domain rules)
          Interactional = can TALK the language (routes/translates)
        """
        if domain in self._experts:
            logger.warning(f"Expert '{domain}' already registered — re-registering")

        quality_multiplier = self.philosophy["uncertainty_calibration"][
            "source_quality_multipliers"
        ].get(source_quality, 0.5)

        self._experts[domain] = {
            "domain": domain,
            "title": title,
            "description": description,
            "cpg_source": cpg_source,
            "source_quality": source_quality,
            "quality_multiplier": quality_multiplier,
            "parent_domain": parent_domain,
            "agent_type": agent_type,
            "rule_count": 0,
            "inference_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            # Goldman trust metrics
            "track_record": 0.0,
            "dialectical_performance": 0.0,
            "peer_agreement": 0.0,
            # Interactional: terminology map for cross-domain translation
            "terminology_map": {},
            # Cross-consultation stats
            "consultations_received": 0,
            "consultations_given": 0,
        }

        logger.info(
            f"Registered expert: {title} ({domain}) "
            f"[agent_type={agent_type}, quality={source_quality}]"
        )
        return self._experts[domain]

    def _count_rules(self, domain: str) -> int:
        """Count production rules for a domain from the DB."""
        if not self.db:
            return 0
        try:
            import json as _json
            from sqlalchemy import text as _sa_text
            row = self.db.execute(
                _sa_text("SELECT COUNT(*) FROM context_objects WHERE type='rule' AND status='active' AND tags LIKE :p"),
                {"p": f"%domain:{domain}%"},
            ).scalar()
            return row or 0
        except Exception:
            return 0

    def list_experts(self) -> List[Dict]:
        """List all registered domain experts with Goldman trust metrics."""
        return [
            {
                "domain": k,
                "title": v["title"],
                "description": v["description"],
                "agent_type": v["agent_type"],
                "rule_count": self._count_rules(k),
                "inference_count": v["inference_count"],
                "source_quality": v["source_quality"],
                "status": v["status"],
                # Goldman (2001) three trust indicators
                "track_record": round(v["track_record"], 3),
                "dialectical_performance": round(v["dialectical_performance"], 3),
                "peer_agreement": round(v["peer_agreement"], 3),
                "overall_trust": round(
                    (v["track_record"] + v["dialectical_performance"] + v["peer_agreement"]) / 3, 3
                ),
            }
            for k, v in self._experts.items()
        ]

    def get_expert(self, domain: str) -> Optional[Dict]:
        """Get metadata for a specific expert."""
        return self._experts.get(domain)

    # ── Goldman (2001) Trust Metrics ──

    def update_track_record(self, domain: str, success: bool) -> None:
        """Update track record: proportion of successful inferences.

        Goldman (2001): past performance is the strongest trust indicator.
        """
        expert = self._experts.get(domain)
        if not expert:
            return
        n = expert["inference_count"]
        if n == 0:
            expert["track_record"] = 1.0 if success else 0.0
        else:
            expert["track_record"] = (
                expert["track_record"] * n + (1.0 if success else 0.0)
            ) / (n + 1)
        expert["inference_count"] = n + 1

    def update_dialectical_performance(self, domain: str, conflict_won: bool) -> None:
        """Update dialectical performance: proportion of conflicts resolved favorably.

        Goldman (2001): how well does the expert defend their position
        when challenged by peers?
        """
        expert = self._experts.get(domain)
        if not expert:
            return
        total = expert.get("conflict_total", 0) + 1
        won = expert.get("conflict_won", 0) + (1 if conflict_won else 0)
        expert["conflict_total"] = total
        expert["conflict_won"] = won
        expert["dialectical_performance"] = won / total if total > 0 else 0.0

    def update_peer_agreement(self, domain: str, peer_domain: str, agreed: bool) -> None:
        """Update peer agreement: proportion of cross-expert consultations where peers agree.

        Goldman (2001): agreement with other recognized experts
        is a strong positive signal.
        """
        expert = self._experts.get(domain)
        if not expert:
            return
        total = expert.get("agreement_total", 0) + 1
        agreed_count = expert.get("agreement_count", 0) + (1 if agreed else 0)
        expert["agreement_total"] = total
        expert["agreement_count"] = agreed_count
        expert["peer_agreement"] = agreed_count / total if total > 0 else 0.0

    def get_goldman_trust(self, domain: str) -> Dict:
        """Get the three Goldman trust indicators for an expert."""
        expert = self._experts.get(domain, {})
        return {
            "track_record": round(expert.get("track_record", 0.0), 3),
            "dialectical_performance": round(expert.get("dialectical_performance", 0.0), 3),
            "peer_agreement": round(expert.get("peer_agreement", 0.0), 3),
            "overall_trust": round(
                (expert.get("track_record", 0.0)
                 + expert.get("dialectical_performance", 0.0)
                 + expert.get("peer_agreement", 0.0)) / 3, 3
            ),
            "inference_count": expert.get("inference_count", 0),
        }

    # ── Interactional Agent ──

    def set_terminology_map(self, domain: str, term_map: Dict[str, str]) -> None:
        """Set cross-domain terminology mapping for an interactional agent.

        Example: {"外踝": "lateral malleolus", "压痛": "tenderness"}
        """
        expert = self._experts.get(domain)
        if expert:
            expert["terminology_map"] = term_map

    def translate_for_domain(self, text: str, from_domain: str, to_domain: str) -> str:
        """Translate terminology between domains using interactional agent mappings."""
        from_expert = self._experts.get(from_domain, {})
        to_expert = self._experts.get(to_domain, {})
        from_map = from_expert.get("terminology_map", {})
        to_map = to_expert.get("terminology_map", {})

        result = text
        for term, replacement in {**from_map, **to_map}.items():
            if term.lower() in result.lower():
                result = re.sub(term, replacement, result, flags=re.IGNORECASE)

        return result

    # ── Expert-to-Expert Consultation ──

    async def consult(
        self,
        from_domain: str,
        to_domain: str,
        question: str,
        context: Dict = None,
        urgency: str = "normal",
        user_id: int = 1,
    ) -> Dict:
        """Expert A requests consultation from Expert B.

        Actually queries the target expert's production rules via the DB.
        Returns matched rules with confidence, reasoning trace, and
        the consulted expert's Goldman trust indicators.

        Constraints:
        - Consultation does NOT modify the caller's rules
        - Response is an opinion with confidence, not a directive
        - The calling expert decides whether to adopt the opinion
        """
        if to_domain not in self._experts:
            return {
                "answer": None,
                "confidence": 0.0,
                "reasoning_trace": [f"Expert '{to_domain}' not found in federation"],
                "consulted_expert": None,
                "error": "expert_not_found",
            }

        target = self._experts[to_domain]

        # Abstract the question to find shared cognitive operations
        abstract_op = self._behavior.abstract(question)
        trace = [f"Abstracted query to: {abstract_op}"]

        # Query the target expert's actual production rules from DB
        triggered_rules = []
        if self.db:
            # Try matching by abstract operation first
            triggered_rules = store_match_rules(
                self.db, user_id, abstract_op,
                domain=to_domain, min_confidence=0.3,
            )
            # If no match, try the raw question text
            if not triggered_rules and abstract_op != question:
                triggered_rules = store_match_rules(
                    self.db, user_id, question,
                    domain=to_domain, min_confidence=0.3,
                )
                if triggered_rules:
                    trace.append(f"Matched {len(triggered_rules)} rule(s) by raw text")
            else:
                trace.append(f"Matched {len(triggered_rules)} rule(s) by abstract operation")
        else:
            trace.append("No DB session — returning empty result")

        # Build response from matched rules
        high_conf = [r for r in triggered_rules if r.confidence >= 0.7]
        any_conf = triggered_rules

        if high_conf:
            best = high_conf[0]
            result = {
                "answer": best.action,
                "confidence": best.confidence,
                "mode": "s1",
                "matched_rule": best.trigger,
                "reasoning_trace": trace + [
                    f"S1 RPD: matched '{best.trigger[:60]}' (conf={best.confidence:.2f})",
                    f"Expert '{target['title']}' recommends: {best.action}",
                ],
            }
        elif any_conf:
            best = any_conf[0]
            result = {
                "answer": best.action,
                "confidence": best.confidence,
                "mode": "s2",
                "matched_rule": best.trigger,
                "reasoning_trace": trace + [
                    f"S2: best match '{best.trigger[:60]}' (conf={best.confidence:.2f})",
                    f"Consider gathering more information before acting on this recommendation.",
                ],
                "all_rules": [{"trigger": r.trigger, "action": r.action,
                               "confidence": r.confidence} for r in any_conf[:5]],
            }
        else:
            result = {
                "answer": None,
                "confidence": 0.0,
                "mode": "no_match",
                "reasoning_trace": trace + [
                    f"No production rules in '{to_domain}' matched the query.",
                    f"Suggestion: compile relevant CPG for this domain first.",
                ],
            }

        result["consulted_expert"] = to_domain
        result["expert_title"] = target["title"]
        result["abstract_operation"] = abstract_op
        result["goldman_trust"] = self.get_goldman_trust(to_domain)

        # Record consultation
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": from_domain,
            "to": to_domain,
            "question": question[:200],
            "abstract_operation": abstract_op,
            "urgency": urgency,
            "confidence": result["confidence"],
            "mode": result.get("mode", "unknown"),
            "rules_matched": len(triggered_rules),
        }
        self._consultation_log.append(log_entry)

        logger.info(
            f"Consultation: {from_domain} → {to_domain}: "
            f"'{question[:60]}...' (op={abstract_op}, mode={result.get('mode')}, "
            f"rules={len(triggered_rules)}, conf={result['confidence']:.2f})"
        )
        return result

    # ── Cross-Domain Counter-Example Propagation ──

    def propagate_counter_example(
        self,
        source_domain: str,
        counter_text: str,
        source_rule_id: str,
    ) -> List[Dict]:
        """When a counter-example is learned in one domain, check if it's
        relevant to other domains via shared abstract cognitive operations.

        Returns list of {domain, rule_id, relevance_score} for review.
        """
        abstract_op = self._behavior.abstract(counter_text)
        if not abstract_op or abstract_op == counter_text:
            return []

        # Find other domains that share this abstract operation
        alerts = []
        for domain, expert in self._experts.items():
            if domain == source_domain:
                continue
            # Check if this domain has rules matching the abstract operation
            if domain in self._cross_domain_links.get(abstract_op, []):
                alerts.append({
                    "domain": domain,
                    "expert_title": expert["title"],
                    "abstract_operation": abstract_op,
                    "counter_preview": counter_text[:100],
                    "source_rule": source_rule_id,
                    "relevance": "high",
                    "action": "review_rules_for_similar_pattern",
                })
            else:
                alerts.append({
                    "domain": domain,
                    "expert_title": expert["title"],
                    "abstract_operation": abstract_op,
                    "counter_preview": counter_text[:100],
                    "source_rule": source_rule_id,
                    "relevance": "low",
                    "action": "no_action",
                })

        if alerts:
            logger.info(
                f"Cross-domain propagation: {source_domain} → "
                f"{len([a for a in alerts if a['relevance']=='high'])} domains alerted"
            )

        return alerts

    def link_domains_by_operation(self, domain_a: str, domain_b: str, operation: str):
        """Explicitly link two domains that share an abstract cognitive operation."""
        self._cross_domain_links[operation].append(domain_a)
        self._cross_domain_links[operation].append(domain_b)
        self._cross_domain_links[operation] = list(set(self._cross_domain_links[operation]))

    # ── Meta Rules Execution ──

    def execute_meta_rules(self, domain: str, inference_result: InferenceResult) -> List[Dict]:
        """Run meta_rules against an inference result. Returns triggered rules."""
        triggered = []
        meta_rules = self.philosophy.get("meta_rules", [])

        for rule in meta_rules:
            if self._meta_rule_matches(rule, inference_result):
                triggered.append({
                    "meta_rule_id": rule["id"],
                    "action": rule["action"],
                    "priority": rule["priority"],
                })

        return triggered

    def _meta_rule_matches(self, rule: Dict, result: InferenceResult) -> bool:
        """Check if a meta rule's trigger condition is met."""
        rid = rule["id"]

        if rid == "meta_001":
            # All rules exhausted with low confidence → request cross-domain consult
            return (
                result.mode == "s2"
                and result.confidence < 0.3
                and not result.activated_rules
            )

        if rid == "meta_002":
            # Any activated rule with high counter count (>3 falsifications)
            for r in result.activated_rules:
                if isinstance(r, dict) and r.get("counter_example_count", 0) > 3:
                    return True
            return False

        if rid == "meta_003":
            # New CPG version detected → need to recompile, diff, flag conflicts
            # Triggered when a rule's source has been superseded by a newer version
            for r in result.activated_rules:
                if isinstance(r, dict):
                    cpg_ref = r.get("source", "")
                    if "updated" in cpg_ref.lower() or "revision" in cpg_ref.lower():
                        return True
                    # Also trigger if rule confidence was high but suddenly dropped
                    if r.get("stage") == "stable" and r.get("counter_example_count", 0) >= 2:
                        return True
            return False

        if rid == "meta_004":
            # Cross-domain same cognitive operation → link domains and share counter-examples
            # Triggered when an abstract operation appears in rules from multiple domains
            ops_seen = set()
            for r in result.activated_rules:
                if isinstance(r, dict):
                    op = r.get("abstract_operation", "")
                    if op and op in ops_seen:
                        return True  # same op from different domains
                    if op:
                        ops_seen.add(op)
            return False

        if rid == "meta_005":
            # Confidence below 0.2 → archive rule, provide three-stances explanation
            return (
                result.mode in ("s2", "no_match")
                and result.confidence < 0.2
            )

        if rid == "meta_006":
            # S2 mode with missing info → ask structured questions, don't fabricate
            return result.mode == "s2" and bool(result.missing_info)

        if rid == "meta_007":
            # System high confidence vs external gold standard low confidence
            # → meta-ignorance alert (system may be confidently wrong)
            for r in result.activated_rules:
                if isinstance(r, dict):
                    ext_conf = r.get("external_gold_standard_confidence")
                    if ext_conf is not None and r.get("confidence", 0) > 0.7 and ext_conf < 0.3:
                        return True
            return False

        return False

    # ── Source Quality Integration ──

    def get_quality_multiplier(self, domain: str) -> float:
        """Get the evidence quality multiplier for a domain."""
        expert = self._experts.get(domain, {})
        return expert.get("quality_multiplier", 1.0)

    def confidence_to_natural_language(self, confidence: float) -> str:
        """Map a confidence score to human-readable language."""
        bands = self.philosophy.get("uncertainty_calibration", {}).get("confidence_to_language", {})
        for band, text in sorted(bands.items(), reverse=True):
            lo, hi = map(float, band.split("-"))
            if lo <= confidence <= hi:
                return text
        return "Unknown confidence level"

    # ── Three Stances ──

    def build_three_stances(
        self,
        domain: str,
        activated_rules: List[Dict],
        confidence: float,
        reasoning_trace: List[str],
    ) -> Dict:
        """Generate simultaneous explanations at all three stances.

        Physical: which rules fired, with what confidence
        Design: why the architecture decided this way
        Intentional: what this means for the user in plain language
        """
        expert = self._experts.get(domain, {})

        physical = {
            "rules_fired": len(activated_rules),
            "confidence": confidence,
            "trace": reasoning_trace,
            "expert_domain": domain,
            "expert_title": expert.get("title", domain),
        }

        design = {
            "architecture": "Minta Expert Federated System",
            "reasoning_mode": "S1" if confidence >= 0.7 else "S2",
            "source_quality": expert.get("source_quality", "unknown"),
            "quality_multiplier": expert.get("quality_multiplier", 1.0),
            "cross_domain_consulted": bool(self._consultation_log),
            "philosophy_version": self.philosophy.get("version", "1.0"),
            "epistemic_principle": (
                "abduction + falsification" if confidence < 0.7
                else "production compilation (ACT-R)"
            ),
        }

        # Build intentional stance: plain-language narrative
        lang = self.confidence_to_natural_language(confidence)
        expert_name = expert.get("title", domain)
        rule_descriptions = [
            f"{r.get('trigger', '?')[:60]} → {r.get('action', '?')[:40]}"
            for r in activated_rules[:3]
        ]

        if confidence >= 0.7:
            narrative = (
                f"The {expert_name} is confident in this recommendation. "
                f"It is based on {len(activated_rules)} matching rule(s): "
                f"{'; '.join(rule_descriptions)}. "
                f"Evidence quality: {expert.get('source_quality', 'standard')}."
            )
        elif confidence >= 0.3:
            narrative = (
                f"The {expert_name} has moderate confidence. "
                f"{len(activated_rules)} rule(s) partially match, but there are gaps. "
                f"Consider consulting additional sources or another domain expert."
            )
        else:
            narrative = (
                f"The {expert_name} is uncertain. "
                f"No rules match with sufficient confidence. "
                f"The system recommends: (1) seek cross-domain consultation, "
                f"(2) provide additional information, (3) consult external guidelines."
            )

        intentional = {
            "narrative": narrative,
            "confidence_level": lang,
            "matched_rules": rule_descriptions,
        }

        return {
            "physical": physical,
            "design": design,
            "intentional": intentional,
        }

    # ── Competence Boundary ──

    def check_competence_boundary(
        self,
        domain: str,
        confidence: float,
        external_gold_standard_confidence: Optional[float] = None,
    ) -> Dict:
        """Check if the system is operating within its competence boundary.

        Returns {within_boundary, meta_ignorance_alert, action}.
        """
        result = {
            "within_boundary": True,
            "meta_ignorance_alert": False,
            "action": "proceed",
        }

        # Confidence too low → outside boundary
        if confidence < 0.2:
            result["within_boundary"] = False
            result["action"] = "suspend_recommendation"
            return result

        # Meta-ignorance check: system is confident but external gold standard disagrees
        if (
            external_gold_standard_confidence is not None
            and confidence > 0.7
            and external_gold_standard_confidence < 0.3
        ):
            result["meta_ignorance_alert"] = True
            result["action"] = "flag_for_review"
            logger.warning(
                f"Meta-ignorance alert for {domain}: "
                f"system_confidence={confidence:.2f}, "
                f"external_confidence={external_gold_standard_confidence:.2f}"
            )

        return result

    # ── Falsification Tracking ──

    def record_falsification_attempt(
        self,
        domain: str,
        rule_id: str,
        survived: bool,
        counter_text: str = "",
    ) -> Dict:
        """Record a falsification attempt against a rule.

        A 'well-formed' counter-example must satisfy three criteria:
        1. Reliably observed
        2. Within rule's declared scope
        3. Excludes alternative explanations (no confounders)
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "rule_id": rule_id,
            "survived": survived,
            "counter_text": counter_text[:200] if counter_text else "",
            "falsification_criteria_met": False,
        }

        if not survived:
            # Evaluate whether the counter meets falsification criteria
            record["falsification_criteria_met"] = self._evaluate_falsification_criteria(
                counter_text
            )

        # Store in expert's falsification history
        expert = self._experts.get(domain, {})
        history = expert.setdefault("falsification_history", [])
        history.append(record)
        expert["falsification_history"] = history[-100:]  # keep last 100

        return record

    def _evaluate_falsification_criteria(self, counter_text: str) -> bool:
        """Evaluate Popperian falsification criteria for a counter-example."""
        criteria = self.philosophy["pillars"]["falsification"]["falsification_criteria"]
        # Simple heuristic: counter text must be substantive enough
        if not counter_text or len(counter_text) < 20:
            return False
        # Check for reliability markers
        has_source = any(
            kw in counter_text.lower()
            for kw in ["study", "trial", "observed", "reported", "documented", "研究", "报告"]
        )
        has_specifics = len(counter_text.split()) > 5
        return has_source or has_specifics

    def get_falsification_history(self, domain: str) -> List[Dict]:
        """Get falsification history for a domain expert."""
        return self._experts.get(domain, {}).get("falsification_history", [])

    def get_corroboration(self, domain: str) -> float:
        """Compute corroboration score: survived_attempts / total_attempts."""
        history = self.get_falsification_history(domain)
        if not history:
            return 0.0
        survived = sum(1 for h in history if h.get("survived", False))
        return survived / len(history)

    # ── Philosophy Query ──

    def get_principle(self, principle_name: str) -> Optional[Dict]:
        """Query a specific philosophical principle."""
        for category in [
            "epistemic_principles", "reasoning_norms", "knowledge_architecture",
            "integrity_principles", "judgment_framework", "agency_and_identity",
        ]:
            if principle_name in self.philosophy.get(category, {}):
                return self.philosophy[category][principle_name]
        return None

    def get_philosophy_summary(self) -> Dict:
        """Return a summary of the Meta-Philosophy for display."""
        return {
            "epistemic_principles": list(self.philosophy["epistemic_principles"].keys()),
            "reasoning_norms": list(self.philosophy["reasoning_norms"].keys()),
            "knowledge_architecture": list(self.philosophy["knowledge_architecture"].keys()),
            "meta_rules_count": len(self.philosophy["meta_rules"]),
            "active_experts": list(self._experts.keys()),
            "cross_domain_links": dict(self._cross_domain_links),
            "consultation_count": len(self._consultation_log),
        }


# Module singleton
_meta_expert: Optional[MetaExpert] = None


def get_meta_expert(db: DBSession = None) -> MetaExpert:
    global _meta_expert
    if _meta_expert is None:
        _meta_expert = MetaExpert(db)
    return _meta_expert
