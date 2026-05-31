"""Minta Expert Inference Engine — S1 fast matching + S2 gap detection + confidence gating.

Integrates all Layer 0-3 modules:
- Layer 0 (Task State Graph): working memory for current reasoning session
- Layer 1 (Context Objects): long-term memory via context objects
- Layer 2 (Production Rules): compiled procedural knowledge
- Layer 3 (CBR 4R): Retrieve → Reuse → Revise → Retain

Dual Process (Kahneman):
- S1: fast rule matching (confidence >= 0.7) → script execution
- S2: slow gap detection + structural reasoning (confidence < 0.7) → hypothesis generation
"""
from __future__ import annotations
import logging
from typing import List, Optional, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session as DBSession
from schemas.task_state import TaskState, Hypothesis, DecisionStep, InferenceResult
from schemas.production_rule import ProductionRule
from services.behavior_abstraction import BehaviorAbstraction
from services.production_store import match_rules, list_rules
from services.task_state_manager import TaskStateManager
from services.meta_expert import get_meta_expert
from services.conformal_predictor import ConformalPredictor
from services.sme_engine import SMEEngine
from models.context_object import ContextObject
from models.inference_log import InferenceLog
from models.skill import Skill

logger = logging.getLogger(__name__)

S1_CONFIDENCE_THRESHOLD = 0.7  # High confidence → S1 fast path
S2_MIN_CONFIDENCE = 0.3       # Minimum to consider at all

# Counter-example keywords — if user previously corrected similar action
_CE_ACTION_PENALTY = 0.3  # How much a counter-example reduces rule confidence

# State consistency thresholds
SIMILARITY_PASS = 0.85
SIMILARITY_FLAG = 0.6


class MintaExpertInference:
    """Dual-process inference engine for expert decision support."""

    def __init__(
        self,
        db: DBSession,
        task_state_manager: TaskStateManager,
        behavior_abstraction: Optional[BehaviorAbstraction] = None,
    ):
        self.db = db
        self.tsm = task_state_manager
        self.abstraction = behavior_abstraction or BehaviorAbstraction()
        self._meta = None
        self._sme = None
        self._conformal = None
        self._sme_initialized = False

    def _get_meta(self):
        if self._meta is None:
            self._meta = get_meta_expert(self.db)
        return self._meta

    def _get_sme(self):
        if not self._sme_initialized:
            try:
                self._sme = SMEEngine()
                self._sme.build_graph(self.db, 0)
            except Exception as e:
                logger.debug(f"SME init skipped: {e}")
            self._sme_initialized = True
        return self._sme

    def _get_conformal(self):
        if self._conformal is None:
            self._conformal = ConformalPredictor()
        return self._conformal

    async def infer(
        self,
        user_message: str,
        session_id: str,
        user_id: int,
        domain: Optional[str] = None,
    ) -> InferenceResult:
        """Run inference on a user message.

        Args:
            user_message: The user's current message/query
            session_id: Current session identifier
            user_id: Authenticated user ID
            domain: Optional domain filter (e.g. "ankle_injury")

        Returns:
            InferenceResult with activated rules, suggestions, missing info, etc.
        """
        trace: List[str] = []

        # Step 1: Abstract the user message
        abstract_action = self.abstraction.abstract(user_message)
        trace.append(f"Abstracted: '{user_message[:60]}' → {abstract_action}")

        # Step 2: S1 — Match compiled production rules
        rules = match_rules(
            self.db, user_id, abstract_action,
            domain=domain, min_confidence=S2_MIN_CONFIDENCE,
        )
        if not rules and user_message:
            rules = match_rules(
                self.db, user_id, user_message,
                domain=domain, min_confidence=S2_MIN_CONFIDENCE,
            )
        trace.append(f"S1 match: {len(rules)} rules found")

        # Step 2b: Check counter-examples against matched rules
        ce_warnings = self._check_counter_examples(user_id, rules, domain)
        if ce_warnings:
            for cw in ce_warnings:
                trace.append(f"Counter-example: {cw}")
        else:
            trace.append("Counter-examples: none found")

        # Step 2c: Search Knowledge Base for relevant context
        kb_entries = self._search_knowledge_base(user_message, user_id, domain)
        if kb_entries:
            for kb in kb_entries[:3]:
                trace.append(f"KB: {kb['title'][:40]} ({kb['type']})")
        else:
            trace.append("KB: no entries found")

        # Step 3: Get current Task State
        task_state = self.tsm.get_current_state(session_id)
        if not task_state.active_task and user_message:
            task_state = self.tsm.create_task(
                session_id, user_message, domain=domain or "",
            )
            trace.append("Created new task from user message")

        # Step 4: S1 RPD — Single solution + mental simulation (Klein 1989)
        high_conf_rules = [r for r in rules if r.confidence >= S1_CONFIDENCE_THRESHOLD]
        if high_conf_rules:
            trace.append(f"S1 RPD: {len(high_conf_rules)} high-confidence rule(s)")

            # RPD Step 1: Recognize → select single best-fit rule (not compare all)
            best_rule = self._rpd_recognize(high_conf_rules, user_message, task_state)

            # RPD Step 2: Mental simulation — does this action make sense?
            simulation_ok = self._rpd_simulate(best_rule, user_message, task_state)

            if simulation_ok:
                trace.append(f"RPD simulation OK: {best_rule.trigger[:50]} → {best_rule.action[:40]}")
                result = await self._s1_rpd_response(
                    best_rule, task_state, session_id, trace,
                    user_id=user_id, domain=domain or "",
                )
                return self._post_process(result, user_message, user_id, domain or "")
            else:
                trace.append("RPD simulation FAILED → fallback to S2")
                # Fall through to S2

        # Step 5: S2 — Gap detection + multi-hypothesis analysis
        trace.append("S2 mode: gap detection + hypothesis generation")
        result = await self._s2_response(
            rules, task_state, session_id, user_message, domain, trace,
            user_id=user_id,
        )
        return self._post_process(result, user_message, user_id, domain or "")

    def _post_process(self, result: InferenceResult, user_message: str,
                      user_id: int, domain: str) -> InferenceResult:
        """Post-processing: meta-rules, conformal gating, SME analogies."""
        try:
            meta = self._get_meta()
        except Exception:
            meta = None

        # 1. Execute meta-rules
        if meta:
            try:
                meta_violations = meta.execute_meta_rules(domain, result)
                if meta_violations:
                    for v in meta_violations[:3]:
                        detail = v.get("detail", v.get("rule", ""))
                        result.reasoning_trace.append(f"Meta-rule: {detail}")
            except Exception as e:
                logger.debug(f"Meta-rules failed: {e}")

        # 2. Conformal prediction confidence gate
        try:
            cp = self._get_conformal()
            if cp.is_calibrated(domain):
                cp_result = cp.predict(domain, result.confidence)
                if cp_result and cp_result.get("p_value", 1.0) < 0.05:
                    result.reasoning_trace.append(
                        f"Conformal: p={cp_result['p_value']:.3f}, confidence adjusted"
                    )
                    result.confidence = round(result.confidence * 0.8, 3)
        except Exception as e:
            logger.debug(f"Conformal gate failed: {e}")

        # 3. SME analogical retrieval
        try:
            sme = self._get_sme()
            if sme and result.activated_rules:
                other_domains = [d for d in ["ankle_injury", "knee_injury",
                                  "cervical_spine_injury"] if d != domain]
                for od in other_domains:
                    analogies = sme.find_analogies(domain, od, top_k=1)
                    if analogies:
                        sim = getattr(analogies[0], "similarity", 0.5)
                        result.reasoning_trace.append(
                            f"SME: {od} similarity={sim:.2f}"
                        )
                        # Attach to analogous_cases
                        if hasattr(analogies[0], "dict"):
                            result.analogous_cases.append(analogies[0].dict())
        except Exception as e:
            logger.debug(f"SME analogies failed: {e}")

        # 4. Write inference_log (async safe — sync DB write)
        log_id = None
        try:
            log_id = self._write_log(result, user_message, user_id, domain)
        except Exception as e:
            logger.debug(f"Inference log write failed: {e}")

        object.__setattr__(result, '_feedback_id', log_id)
        return result

    def update_log_feedback(self, user_id: int, domain: str,
                             signal: str, session_id: str = "") -> None:
        """Update the inference_log entry matching session+domain with feedback."""
        try:
            q = self.db.query(InferenceLog).filter(
                InferenceLog.user_id == user_id,
                InferenceLog.domain == domain,
                InferenceLog.user_signal.is_(None),
            )
            if session_id:
                q = q.filter(InferenceLog.session_id == session_id)
            log = q.order_by(InferenceLog.id.desc()).first()
            if log:
                log.user_signal = signal
                log.feedback_at = datetime.now(timezone.utc)
                self.db.commit()
        except Exception as e:
            logger.error(f"Failed to update inference_log feedback: {e}")

    def _write_log(self, result: InferenceResult, user_message: str,
                   user_id: int, domain: str) -> None:
        """Persist inference to inference_log table."""
        log = InferenceLog(
            user_id=user_id,
            domain=domain,
            session_id=getattr(result, '_session_id', ''),
            user_message=user_message[:1000],
            abstract_action=result.reasoning_trace[0].replace("Abstracted: ", "")[:100]
            if result.reasoning_trace and "Abstracted" in result.reasoning_trace[0]
            else "",
            matched_rules=[
                {"trigger": r.get("trigger",""), "action": r.get("action",""),
                 "confidence": r.get("confidence",0)}
                for r in (result.activated_rules if isinstance(result.activated_rules, list) else [])[:5]
            ] if result.activated_rules else None,
            confidence=result.confidence,
            mode=result.mode,
            suggested_step=result.suggested_next_step[:500] if result.suggested_next_step else "",
            missing_info=result.missing_info if result.missing_info else None,
            rule_ids=[
                r.get("id","") for r in
                (result.activated_rules if isinstance(result.activated_rules, list) else [])[:5]
                if isinstance(r, dict) and r.get("id")
            ] if result.activated_rules else None,
            audit_verdict="pass",
        )
        self.db.add(log)
        try:
            self.db.commit()
            self.db.refresh(log)
            return log.id
        except Exception:
            self.db.rollback()
            return None

    def _search_knowledge_base(self, text: str, user_id: int, domain: Optional[str] = None) -> List[Dict]:
        """Search knowledge base (Context Objects) for relevant entries."""
        try:
            q = self.db.query(ContextObject).filter(
                ContextObject.user_id == user_id,
                ContextObject.status == "active",
            )
            if domain:
                q = q.filter(ContextObject.tags.any(f"domain:{domain}"))
            entries = q.order_by(ContextObject.updated_at.desc()).limit(20).all()

            text_lower = text.lower()
            scored = []
            for e in entries:
                # Simple text overlap scoring
                score = 0
                for field in [e.title or "", e.summary or "", e.body or ""]:
                    field_lower = field.lower()
                    words = text_lower.split()
                    matches = sum(1 for w in words if len(w) > 2 and w in field_lower)
                    score += matches / max(len(words), 1)
                if score > 0:
                    scored.append({"title": e.title, "summary": e.summary or "",
                                   "type": e.type, "score": round(score, 2)})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:5]
        except Exception as e:
            logger.debug(f"KB search failed: {e}")
            return []

    def _check_counter_examples(self, user_id: int, rules: list, domain: Optional[str] = None) -> List[str]:
        """Check if any counter-examples (lesson_learned) contradict activated rules."""
        warnings = []
        try:
            ces = self.db.query(ContextObject).filter(
                ContextObject.user_id == user_id,
                ContextObject.type == "lesson_learned",
                ContextObject.status == "active",
            ).all()
            if not ces or not rules:
                return warnings

            for rule in rules:
                rule_text = f"{rule.trigger or ''} {rule.action or ''}".lower()
                for ce in ces:
                    ce_text = f"{ce.title or ''} {ce.summary or ''} {ce.body or ''}".lower()
                    # If counter-example shares significant overlap with rule action
                    if rule.action and rule.action.lower() in ce_text:
                        warnings.append(f"规则[{rule.action[:30]}]有相关反例，已降低置信度")
                        rule.confidence = max(0.1, rule.confidence - _CE_ACTION_PENALTY)
        except Exception as e:
            logger.debug(f"Counter-example check failed: {e}")
        return warnings

    def _find_relevant_skills(self, domain: Optional[str], user_id: int) -> List[str]:
        """Find skills related to the inference domain."""
        try:
            q = self.db.query(Skill).filter(
                Skill.user_id == user_id,
            )
            skills = q.all()
            matched = []
            for s in skills:
                s_text = f"{s.name} {s.name_zh or ''} {s.description or ''}".lower()
                if domain and domain.replace("_", " ") in s_text:
                    matched.append(s.name)
                elif s.name and ("expert" in s.name.lower() or "decision" in s.name.lower()):
                    matched.append(s.name)
            return matched[:3]
        except Exception as e:
            logger.debug(f"Skills search failed: {e}")
            return []

    def _rpd_recognize(
        self,
        high_conf_rules: List[ProductionRule],
        user_message: str,
        task_state: TaskState,
    ) -> ProductionRule:
        """RPD Step 1: Recognize the situation and generate ONE course of action.

        Klein's RPD model: experts do NOT compare options.
        They recognize a familiar situation and immediately retrieve
        the most relevant action pattern.
        """
        if len(high_conf_rules) == 1:
            return high_conf_rules[0]

        # Multiple high-conf rules: select the one with best trigger overlap
        best = high_conf_rules[0]
        best_overlap = 0
        msg_lower = user_message.lower()
        for rule in high_conf_rules:
            trigger_lower = (rule.trigger or "").lower()
            overlap = sum(
                1 for word in trigger_lower.split()
                if word in msg_lower
            )
            # Prefer rules that match the current task context
            if rule.trigger in task_state.active_task:
                overlap += 5
            if overlap > best_overlap:
                best_overlap = overlap
                best = rule

        return best

    def _rpd_simulate(
        self,
        rule: ProductionRule,
        user_message: str,
        task_state: TaskState,
    ) -> bool:
        """RPD Step 2: Mental simulation — would this action work?

        Checks:
        1. Is the rule's trigger actually present in the user's message?
        2. Is there any contradictory evidence in the task state?
        3. Does the action make logical sense (no self-contradiction)?
        """
        # Check 1: Trigger relevance
        trigger_keywords = set(
            w.lower() for w in (rule.trigger or "").split()
            if len(w) > 2
        )
        msg_lower = user_message.lower()
        trigger_hits = sum(1 for kw in trigger_keywords if kw in msg_lower)
        if trigger_hits == 0 and len(trigger_keywords) > 2:
            return False  # trigger not present in message

        # Check 2: No contradictory evidence in task state
        for hypothesis in task_state.confirmed_hypotheses + task_state.rejected_hypotheses:
            if hasattr(hypothesis, 'description'):
                hyp_lower = hypothesis.description.lower()
                # If a confirmed hypothesis contradicts the rule's action
                if rule.action and rule.action.lower() in hyp_lower and "不建议" in hyp_lower:
                    return False

        # Check 3: Action doesn't contradict itself
        if "不建议" in (rule.action or "") and "建议" in (rule.action or "").replace("不建议", ""):
            return False

        return True

    async def _s1_rpd_response(
        self,
        best_rule: ProductionRule,
        task_state: TaskState,
        session_id: str,
        trace: List[str],
        user_id: int = 0,
        domain: str = "",
    ) -> InferenceResult:
        """S1 RPD response: single-solution output with confidence."""
        skills = self._find_relevant_skills(domain, user_id)
        for sk in skills:
            trace.append(f"Skill: {sk}")

        step = DecisionStep(
            step=best_rule.trigger,
            result=best_rule.action,
            rule_id=best_rule.id,
            timestamp=datetime.now(timezone.utc),
        )
        self.tsm.push_step(session_id, step)

        return InferenceResult(
            activated_rules=[best_rule.dict()],
            suggested_next_step=best_rule.action,
            missing_info=[],
            confidence=round(best_rule.confidence, 3),
            mode="s1",
            reasoning_trace=trace + [
                f"RPD: recognized {best_rule.trigger[:50]}",
                f"RPD: simulated → action: {best_rule.action[:50]}",
            ],
        )

    async def _s2_response(
        self,
        rules: List[ProductionRule],
        task_state: TaskState,
        session_id: str,
        user_message: str,
        domain: Optional[str],
        trace: List[str],
        user_id: int = 0,
    ) -> InferenceResult:
        """S2 slow path: detect gaps, generate hypotheses."""
        gaps = self._detect_gaps(task_state, rules)

        # If no active hypotheses, generate one from the user message
        if not task_state.active_hypotheses and gaps:
            for gap in gaps[:3]:
                hyp = Hypothesis(
                    id=f"hyp_{len(task_state.active_hypotheses)}",
                    description=f"需要考虑: {gap}",
                    confidence=0.5,
                )
                self.tsm.add_hypothesis(session_id, hyp)
                trace.append(f"Generated hypothesis: {hyp.description[:60]}")

        # Suggest next step
        suggestion = self._suggest_next_step(rules, gaps, task_state)
        if suggestion:
            trace.append(f"Suggested: {suggestion[:60]}")

        # Step 6: Add skills knowledge
        skills = self._find_relevant_skills(domain, user_id)
        for sk in skills:
            trace.append(f"Skill: {sk}")

        avg_conf = sum(r.confidence for r in rules) / len(rules) if rules else 0.0
        return InferenceResult(
            activated_rules=[r.dict() for r in rules[:5]],
            suggested_next_step=suggestion,
            missing_info=gaps,
            analogous_cases=[],
            task_state_update={
                "active_hypotheses": [h.dict() for h in task_state.active_hypotheses],
                "pending_questions": task_state.pending_questions,
            },
            confidence=round(avg_conf, 3),
            mode="s2",
            reasoning_trace=trace,
        )

    def _detect_gaps(
        self,
        task_state: TaskState,
        rules: List[ProductionRule],
    ) -> List[str]:
        """Detect information gaps in the current reasoning state."""
        gaps = []

        # Check if task is defined
        if not task_state.active_task:
            gaps.append("任务尚未定义")
            return gaps

        # Check for hypotheses
        if not task_state.active_hypotheses:
            gaps.append("未形成任何待验证的假设")

        # Check if we've exhausted all rule conditions
        completed_steps = {s.step for s in task_state.decision_stack}
        for rule in rules:
            if rule.trigger and rule.trigger not in completed_steps:
                gaps.append(f"规则条件未评估: {rule.trigger}")

        # Check unanswered questions
        if task_state.pending_questions:
            gaps.append(f"有 {len(task_state.pending_questions)} 个待回答问题")

        return gaps

    def _suggest_next_step(
        self,
        rules: List[ProductionRule],
        gaps: List[str],
        task_state: TaskState,
    ) -> Optional[str]:
        """Suggest the next reasoning step based on rules and gaps."""
        # If there are high-confidence rules not yet applied, suggest them
        if rules:
            best = rules[0]
            if best.trigger not in {s.step for s in task_state.decision_stack}:
                return f"应用规则: {best.trigger} → {best.action}"

        # If gaps exist, suggest filling the first one
        if gaps:
            return f"需补充信息: {gaps[0]}"

        # If hypotheses exist but none confirmed, suggest validation
        active = [h for h in task_state.active_hypotheses if h.status == "active"]
        if active:
            return f"建议验证假设: {active[0].description[:80]}"

        return None
