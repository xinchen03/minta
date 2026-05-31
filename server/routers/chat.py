"""Minta Chat Router — natural-language triage with expert activation and trust tracking.

Endpoints:
  POST   /api/chat            Chat with domain detection, expert suggestion, activation
  POST   /api/chat/trust      Record trust signal from conversation
  GET    /api/chat/domains    List available domains for chat detection
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user

from services.meta_expert import get_meta_expert, MetaExpert
from services.inference_engine import MintaExpertInference
from services.task_state_manager import TaskStateManager
from services.behavior_abstraction import BehaviorAbstraction
from services.embedding_service import get_embedding_service
from services.production_store import run_4r_cycle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Domain detection keyword maps ──
# Each domain is paired with medical keywords (Chinese + English) for matching
DOMAIN_KEYWORDS: Dict[str, Dict] = {
    "ankle_injury": {
        "label": "踝关节损伤",
        "keywords": [
            "脚踝", "踝关节", "外踝", "内踝", "距骨", "跟腱",
            "ankle", "malleolus", "talus", "achilles", "lateral ankle",
        ],
    },
    "knee_injury": {
        "label": "膝关节损伤",
        "keywords": [
            "膝盖", "膝关节", "半月板", "髌骨", "前交叉", "后交叉",
            "knee", "patella", "meniscus", "acl", "pcl", "mcl", "lcl",
        ],
    },
    "cervical_spine_injury": {
        "label": "颈椎损伤",
        "keywords": [
            "颈椎", "脖子", "颈部", "颈痛", "落枕",
            "cervical", "c-spine", "neck", "whiplash",
        ],
    },
    "concussion": {
        "label": "脑震荡",
        "keywords": [
            "脑震荡", "头晕", "头痛", "意识丧失", " concussion",
            "head injury", "tbi", "dizziness",
        ],
    },
    "shoulder_injury": {
        "label": "肩关节损伤",
        "keywords": [
            "肩膀", "肩关节", "肩袖", "肩峰",
            "shoulder", "rotator cuff", "acromion",
        ],
    },
}

# ── Lazy-init singletons ──
_task_state_manager: Optional[TaskStateManager] = None
_behavior_abstraction: Optional[BehaviorAbstraction] = None
_inference_engine: Optional[MintaExpertInference] = None


def _get_tsm() -> TaskStateManager:
    global _task_state_manager
    if _task_state_manager is None:
        _task_state_manager = TaskStateManager()
    return _task_state_manager


def _get_ba() -> BehaviorAbstraction:
    global _behavior_abstraction
    if _behavior_abstraction is None:
        _behavior_abstraction = BehaviorAbstraction()
    return _behavior_abstraction


def _get_engine(db: DBSession) -> MintaExpertInference:
    global _inference_engine
    if _inference_engine is None:
        _inference_engine = MintaExpertInference(
            db=db,
            task_state_manager=_get_tsm(),
            behavior_abstraction=_get_ba(),
        )
    return _inference_engine


# ── In-memory trust feedback store ──
# Stores detailed feedback events with timestamps for auditing.
_FEEDBACK_STORE: List[Dict] = []
_MAX_FEEDBACK = 500


# ── Request/Response models ──

class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[int] = None
    activate_expert: Optional[str] = None          # trigger inference directly
    confirmation: Optional[bool] = None            # unused; activate_expert signals intent


class ChatResponse(BaseModel):
    reply: str
    suggested_experts: List[Dict] = []
    requires_confirmation: bool = False
    inference_result: Optional[dict] = None
    federation_suggestion: Optional[str] = None


class TrustSignalRequest(BaseModel):
    session_id: str
    inference_id: Optional[str] = None
    signal: str                                     # positive | negative | neutral
    source_text: str = ""
    domain: Optional[str] = None


class TrustSignalResponse(BaseModel):
    ok: bool
    goldman_updated: bool
    running_track_record: float
    feedback_id: str


# ── Domain detection ──

def _detect_domains(message: str) -> List[Dict]:
    """Match a user message against known expert domains using keywords.

    Returns a sorted list of {domain, label, keyword_count, confidence}
    with confidence computed as: matched_keywords / total_keywords_in_domain
    """
    msg_lower = message.lower()
    results = []

    for domain, info in DOMAIN_KEYWORDS.items():
        matched = [kw for kw in info["keywords"] if kw.lower() in msg_lower]
        if matched:
            # Heuristic confidence: keyword coverage ratio
            ratio = len(matched) / max(len(info["keywords"]), 1)
            # Boost if multiple matches
            coverage = min(1.0, len(matched) * 0.25)
            confidence = round(max(ratio, coverage), 3)
            # Cap at 0.95 (never 100% certain from keywords alone)
            confidence = min(confidence, 0.95)

            results.append({
                "domain": domain,
                "label": info["label"],
                "matched_keywords": matched,
                "keyword_count": len(matched),
                "confidence": confidence,
            })

    # Sort by confidence descending
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def _get_domain_rule_count(db: DBSession, domain: str) -> int:
    """Count compiled production rules for a domain in the database."""
    try:
        from sqlalchemy import text as _sa_text
        row = db.execute(
            _sa_text(
                "SELECT COUNT(*) FROM context_objects "
                "WHERE type='rule' AND status='active' AND tags LIKE :p"
            ),
            {"p": f"%domain:{domain}%"},
        ).scalar()
        return row or 0
    except Exception:
        return 0


def _build_domain_suggestions(
    db: DBSession,
    matches: List[Dict],
) -> List[Dict]:
    """Enrich domain matches with rule counts."""
    suggestions = []
    for m in matches:
        rule_count = _get_domain_rule_count(db, m["domain"])
        suggestions.append({
            "domain": m["domain"],
            "label": m["label"],
            "rule_count": rule_count,
            "confidence": m["confidence"],
        })
    return suggestions


def _build_reply_from_matches(matches: List[Dict]) -> str:
    """Build a natural-language reply suggesting expert activation."""
    if not matches:
        return ""

    top = matches[0]
    domain_label = top["label"]
    domain = top["domain"]

    # Get rule count from meta_expert
    if top.get("rule_count", 0) > 0:
        rule_info = f"{top['rule_count']} 条相关规则"
    else:
        rule_info = "相关规则"

    reply = (
        f"检测到您的问题涉及{domain_label}。"
        f"Minta {domain_label}专家有 {rule_info}，"
        f"需要启动专家推理吗？"
    )
    return reply


def _build_federation_suggestion(
    matches: List[Dict],
    meta: MetaExpert,
) -> Optional[str]:
    """If the top match has low confidence, suggest cross-domain consultation."""
    if not matches:
        return None

    top = matches[0]
    if top["confidence"] >= 0.6:
        return None  # confident enough, no federation needed

    # Check if there is a second domain to suggest
    if len(matches) >= 2:
        second = matches[1]
        second_domain = second["domain"]
        trust = meta.get_goldman_trust(second_domain)

        # Only suggest if the second expert has reasonable trust
        if trust.get("overall_trust", 0) >= 0.3:
            return (
                f"{top['label']}判断可靠度一般"
                f"（置信度={top['confidence']:.0%}），"
                f"需要咨询{second['label']}专家吗？"
            )

    return (
        f"{top['label']}匹配置信度较低"
        f"（{top['confidence']:.0%}），"
        f"请提供更多症状信息以便精准判断。"
    )


# ── Endpoints ──

@router.post("")
async def chat(
    req: ChatRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Process a chat message with domain detection and expert activation.

    Flow:
      1. If `activate_expert` is set → call inference engine directly
      2. Else → detect domain via keyword matching, return suggestion
      3. When confidence is low → suggest cross-domain federation
    """
    if not req.message:
        raise HTTPException(status_code=400, detail="message is required")

    user_id = req.user_id or current_user.id

    # ── Mode A: Multi-stage expert reasoning pipeline ──
    if req.activate_expert:
        domain = req.activate_expert
        try:
            meta = get_meta_expert(db)
            # Auto-register if needed
            if meta.get_expert(domain) is None and domain in DOMAIN_KEYWORDS:
                meta.register_expert(domain=domain, title=DOMAIN_KEYWORDS[domain]["label"],
                    description=f"Auto-registered via chat for {DOMAIN_KEYWORDS[domain]['label']}",
                    agent_type="contributory")

            engine = _get_engine(db)
            engine.db = db

            # ── Stage 1: Inference (S1 fast + S2 gap detection) ──
            result = await engine.infer(
                user_message=req.message, session_id=req.session_id,
                user_id=user_id, domain=domain)
            result_dict = result.dict()
        except Exception as e:
            logger.error(f"Mode A infer failed: {e}")
            return {"ok": True, "data": {
                "reply": f"专家推理暂时不可用，请稍后重试。",
                "reasoning_chain": {"stage_1_s1_s2": {"mode": "error", "error": str(e)}},
                "domain": domain, "confidence": 0.0, "confidence_label": "推理异常",
            }}

        # ── Stage 2: Knowledge Base retrieval (best-effort) ──
        kb_findings = []
        try:
            emb = get_embedding_service()
            kb_results = emb.search(req.message, top_k=3)
            if kb_results:
                for kr in kb_results:
                    kb_findings.append({
                        "title": kr.get("title", "")[:60],
                        "summary": kr.get("summary", "")[:100],
                        "type": kr.get("type", "context"),
                        "similarity": round(kr.get("score", 0), 3),
                    })
        except Exception:
            pass  # KB is optional

        # ── Stage 3: Gap analysis ──
        gaps = []
        try:
            missing = result_dict.get("missing_info") or []
            for m in missing:
                text = str(m).strip()
                # Filter out internal engine messages, keep actionable ones
                if text and "未形成" not in text and "条件未评估" not in text:
                    gaps.append({"question": text, "reason": "missing", "priority": 5})
        except Exception:
            pass

        # ── Stage 4: Cross-domain analogies (best-effort) ──
        analogies = []
        try:
            if result.activated_rules:
                for od in [d for d in DOMAIN_KEYWORDS if d != domain]:
                    if meta.get_expert(od):
                        analogies.append({
                            "source": domain, "target": od,
                            "description": f"与{DOMAIN_KEYWORDS[od]['label']}存在结构关联",
                        })
        except Exception:
            pass

        # ── Stage 5: Federation suggestion ──
        federation = None
        try:
            if result.confidence < 0.6:
                for od in [d for d in DOMAIN_KEYWORDS if d != domain]:
                    trust = meta.get_goldman_trust(od)
                    if trust.get("overall_trust", 0.3) >= 0.3:
                        federation = {"domain": od, "label": DOMAIN_KEYWORDS[od]["label"],
                            "reason": f"主领域匹配度较低({result.confidence:.0%})，建议跨域咨询"}
                        break
        except Exception:
            pass

        # ── Stage 6: Build output ──
        try:
            confidence_label = meta.confidence_to_natural_language(result.confidence)
        except Exception:
            confidence_label = f"{result.confidence:.0%}"
        try:
            three_stances = meta.build_three_stances(domain=domain,
                activated_rules=[r if isinstance(r, dict) else r.dict() for r in result.activated_rules],
                confidence=result.confidence, reasoning_trace=result.reasoning_trace or [])
        except Exception:
            three_stances = {}
        try:
            boundary = meta.check_competence_boundary(domain, result.confidence)
        except Exception:
            boundary = {}
        try:
            meta.update_track_record(domain, result.confidence >= 0.5)
        except Exception:
            pass

        # Build natural-language reply
        reply_parts = []
        if result.suggested_next_step and result.confidence >= 0.7:
            reply_parts.append(result.suggested_next_step)
        elif result.suggested_next_step:
            reply_parts.append(result.suggested_next_step)

        if gaps:
            reply_parts.append(f"还需确认：{'；'.join([g['question'] for g in gaps[:2]])}")

        if kb_findings:
            reply_parts.append(f"参考了{len(kb_findings)}条相关知识")

        if analogies and result.confidence < 0.8:
            for a in analogies[:1]:
                reply_parts.append(f"建议同步咨询{a['description']}")

        reply = "。".join(reply_parts) if reply_parts else \
                (result.suggested_next_step or "已分析完毕，请补充更多症状信息。")

        # Build reasoning chain for UI
        reasoning_chain = {
            "stage_1_s1_s2": {
                "mode": result_dict.get("mode", "s2"),
                "confidence": result.confidence,
                "rules_activated": len(result.activated_rules),
                "rules": [{"trigger": r.get("trigger","")[:60], "action": r.get("action","")[:60]}
                          for r in (result_dict.get("activated_rules") or [])[:5]],
            },
            "stage_2_knowledge_base": kb_findings[:2],
            "stage_3_gap_analysis": gaps[:3],
            "stage_4_analogies": analogies,
            "stage_5_federation": federation,
            "stage_6_metacognition": {
                "confidence_level": confidence_label,
                "competence": boundary.get("judgment", "") if boundary else "",
            },
        }

        return {
            "ok": True,
            "data": {
                "reply": reply,
                "reasoning_chain": reasoning_chain,
                "domain": domain,
                "inference_result": result_dict["activated_rules"][:3] if result_dict.get("activated_rules") else [],
                "confidence": result.confidence,
                "confidence_label": confidence_label,
            },
        }

    # ── Mode B: Domain detection and suggestion ──
    matches = _detect_domains(req.message)

    if not matches:
        return {
            "ok": True,
            "data": {
                "reply": "未检测到匹配的专业领域。请问您能提供更多症状描述吗？",
                "suggested_experts": [],
                "requires_confirmation": False,
                "federation_suggestion": None,
            },
        }

    # Enrich with rule counts from DB
    meta = get_meta_expert(db)
    suggestions = _build_domain_suggestions(db, matches)
    reply = _build_reply_from_matches(suggestions)
    federation = _build_federation_suggestion(matches, meta)

    return {
        "ok": True,
        "data": {
            "reply": reply,
            "suggested_experts": suggestions,
            "requires_confirmation": True,
            "federation_suggestion": federation,
        },
    }


@router.post("/trust")
async def record_trust_signal(
    req: TrustSignalRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Record a trust signal from a conversation interaction.

    Maps user feedback signals to Goldman trust metric updates:
      - positive → increment track_record (success=True)
      - negative → decrement track_record (success=False)
      - neutral  → no change, but record for auditing
    """
    if req.signal not in ("positive", "negative", "neutral"):
        raise HTTPException(status_code=400, detail="signal must be 'positive', 'negative', or 'neutral'")

    meta = get_meta_expert(db)

    # Resolve domain: use explicit domain, or discover from experts list
    domain = req.domain
    if not domain:
        # If no domain specified, try to infer from available experts
        experts = meta.list_experts()
        if experts:
            domain = experts[0]["domain"]

    feedback_id = str(uuid.uuid4())
    goldman_updated = False
    log_updated = False

    # Update Goldman trust metrics
    if domain:
        expert = meta.get_expert(domain)
        if expert:
            if req.signal == "positive":
                meta.update_track_record(domain, success=True)
                goldman_updated = True
            elif req.signal == "negative":
                meta.update_track_record(domain, success=False)
                goldman_updated = True
            # neutral: no Goldman update, just log

        # Update inference_log feedback
        try:
            from services.inference_engine import MintaExpertInference
            from services.task_state_manager import TaskStateManager
            engine = MintaExpertInference(db=db, task_state_manager=TaskStateManager())
            engine.update_log_feedback(
                user_id=current_user.id,
                domain=domain,
                signal=req.signal,
                session_id=req.session_id,
            )
            log_updated = True
        except Exception as e:
            logger.warning(f"InferenceLog feedback update failed: {e}")

    # Store detailed feedback event
    event = {
        "feedback_id": feedback_id,
        "session_id": req.session_id,
        "inference_id": req.inference_id,
        "user_id": current_user.id,
        "domain": domain,
        "signal": req.signal,
        "source_text": req.source_text[:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _FEEDBACK_STORE.append(event)
    if len(_FEEDBACK_STORE) > _MAX_FEEDBACK:
        _FEEDBACK_STORE[:len(_FEEDBACK_STORE) - _MAX_FEEDBACK] = []

    # Compute current running track record
    running_track_record = 0.0
    if domain:
        trust = meta.get_goldman_trust(domain)
        running_track_record = trust.get("track_record", 0.0)

    logger.info(
        f"Trust signal: {req.signal} (domain={domain}, "
        f"track_record={running_track_record:.3f})"
    )

    return {
        "ok": True,
        "data": {
            "goldman_updated": goldman_updated,
            "running_track_record": running_track_record,
            "feedback_id": feedback_id,
            "domain": domain,
            "signal": req.signal,
        },
    }


@router.get("/trust/feedbacks")
async def list_trust_feedbacks(
    domain: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List recent trust feedback events, optionally filtered by domain."""
    events = _FEEDBACK_STORE
    if domain:
        events = [e for e in events if e.get("domain") == domain]
    return {
        "ok": True,
        "data": events[-limit:],
        "count": len(events[-limit:]),
    }


@router.get("/domains")
async def list_chat_domains(
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all domains available for chat detection, with rule counts."""
    results = []
    for domain, info in DOMAIN_KEYWORDS.items():
        rule_count = _get_domain_rule_count(db, domain)
        results.append({
            "domain": domain,
            "label": info["label"],
            "rule_count": rule_count,
            "keyword_count": len(info["keywords"]),
        })
    return {"ok": True, "data": results, "count": len(results)}
