"""Minta Expert API — expert decision support endpoints.

Endpoints:
  POST   /api/expert/infer                 Run inference on user message
  GET    /api/expert/productions           List compiled production rules
  POST   /api/expert/productions/compile   Compile rules from CPG text
  GET    /api/expert/task-state            Get current working memory state
  POST   /api/expert/task-state/hypothesis Add/confirm/reject hypothesis
  DELETE /api/expert/task-state            Clear current task state
"""
from __future__ import annotations
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user
from models.context_object import ContextObject

from services.inference_engine import MintaExpertInference
from services.task_state_manager import TaskStateManager
from services.behavior_abstraction import BehaviorAbstraction
from services.domain_compiler import DomainCompiler
from services.production_store import (
    list_rules, create_rule, compile_from_cpg, update_confidence,
)
from schemas.task_state import Hypothesis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/expert", tags=["expert"])

# ── Lazy-init singletons ──
_task_state_manager: Optional[TaskStateManager] = None
_behavior_abstraction: Optional[BehaviorAbstraction] = None
_domain_compiler: Optional[DomainCompiler] = None
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


def _get_compiler() -> DomainCompiler:
    global _domain_compiler
    if _domain_compiler is None:
        _domain_compiler = DomainCompiler()
    return _domain_compiler


def _get_engine(db: DBSession) -> MintaExpertInference:
    global _inference_engine
    if _inference_engine is None:
        _inference_engine = MintaExpertInference(
            db=db,
            task_state_manager=_get_tsm(),
            behavior_abstraction=_get_ba(),
        )
    return _inference_engine


# ── Request/Response models ──

class InferRequest(BaseModel):
    message: str
    session_id: str
    domain: Optional[str] = None


class CompileRequest(BaseModel):
    cpg_text: str
    domain: str
    source: str = ""


class HypothesisRequest(BaseModel):
    session_id: str
    hypothesis_id: Optional[str] = None
    description: str = ""
    action: str = "add"          # add | confirm | reject
    evidence: str = ""


class RuleUpdateRequest(BaseModel):
    rule_id: str
    delta: float = 0.0            # confidence delta


# ── In-memory activity log (ephemeral, for MVP) ──
_activity_log: list = []
_MAX_ACTIVITY = 100


def _log_activity(event: str, domain: str, detail: str = "", user_id: int = 0):
    """Log an expert system activity event."""
    from datetime import datetime, timezone
    _activity_log.append({
        "event": event,
        "domain": domain,
        "detail": detail,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(_activity_log) > _MAX_ACTIVITY:
        _activity_log[:len(_activity_log) - _MAX_ACTIVITY] = []


# ── Endpoints ──

@router.get("/activity")
async def get_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Get recent expert system activity log."""
    logs = [e for e in _activity_log if e["user_id"] in (0, current_user.id)]
    return {"ok": True, "data": logs[-limit:]}


@router.post("/infer")
async def infer(
    req: InferRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run expert inference on a user message."""
    if not req.message:
        raise HTTPException(status_code=400, detail="message is required")

    engine = _get_engine(db)
    engine.db = db  # refresh db session
    result = await engine.infer(
        user_message=req.message,
        session_id=req.session_id,
        user_id=current_user.id,
        domain=req.domain,
    )

    # ── Run 4R cycle after inference ──
    cbr_trace = None
    try:
        from config import MINTA_EXPERT_ENABLED
        if MINTA_EXPERT_ENABLED and result.activated_rules:
            from services.production_store import run_4r_cycle
            # Convert dict rules to object-like for 4R cycle compatibility
            rules = result.activated_rules
            cbr_trace = run_4r_cycle(
                db, current_user.id,
                query=req.message,
                domain=req.domain or "",
                matched_rules=rules,
            )
    except Exception as e:
        logger.warning(f"CBR 4R skipped: {e}")
        try: db.rollback()
        except: pass

    # ── JEPA temporal verification ──
    jepa_result = None
    try:
        from services.jepa_scheduler import get_jepa_scheduler
        from sentence_transformers import SentenceTransformer

        jepa = get_jepa_scheduler(db)

        # Check training trigger
        if jepa.check_training_trigger(req.domain or "unknown", current_user.id):
            jepa.train_domain(req.domain or "unknown", current_user.id)

        # Temporal prediction
        if jepa.should_predict(req.domain or "unknown", current_user.id):
            # Encode current message
            try:
                emb_model = SentenceTransformer(os.environ.get('MINTA_EMBEDDING_MODEL', 'all-MiniLM-L6-v2'))
                msg_emb = emb_model.encode(req.message)
            except Exception:
                msg_emb = np.zeros(384, dtype=np.float32)

            prediction = jepa.predict(msg_emb, req.domain or "unknown", current_user.id)
            if prediction:
                # Compare expert result vs JEPA prediction
                from services.jepa_world_model import JEPAStateComparator
                comparator = JEPAStateComparator()

                # Use confidence as a simple state proxy
                expert_state = np.ones(128, dtype=np.float32) * result.confidence
                jepa_state = prediction["predicted_emb"]

                similarity, verdict = comparator.cosine_similarity(expert_state, jepa_state), \
                                     comparator.verdict(
                    comparator.cosine_similarity(expert_state, jepa_state)
                )

                jepa_result = {
                    "similarity": round(similarity, 3),
                    "verdict": verdict,
                    "model_trained": prediction["model_trained"],
                    "has_history": prediction["has_history"],
                }

                if verdict == "flag" or verdict == "reject":
                    # Get missing dimensions from history
                    from services.jepa_scheduler import MIN_HISTORY_FOR_PREDICTION
                    if jepa.count_history(req.domain or "unknown") >= MIN_HISTORY_FOR_PREDICTION:
                        from services.jepa_world_model import JEPAStateComparator
                        logs = jepa.get_temporal_sequence(req.domain or "unknown", current_user.id)
                        missing = JEPAStateComparator.get_missing_dimensions(
                            req.domain or "unknown",
                            [{"missing_info": []}]  # placeholder
                        )
                        if missing:
                            jepa_result["missing_dimensions"] = missing
    except Exception as e:
        logger.warning(f"JEPA verification skipped: {e}")

    # Log activity
    _log_activity("inference", req.domain or "unknown",
                  f"{len(result.activated_rules)} rules matched, mode={result.mode}",
                  current_user.id)

    feedback_id = getattr(result, '_feedback_id', None)

    return {"ok": True, "data": {
        **result.dict(),
        "cbr_4r": cbr_trace,
        "jepa_verification": jepa_result,
        "feedback_id": feedback_id,
        "feedback_prompt": feedback_id is not None,
    }}


@router.get("/productions")
async def list_productions(
    domain: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List compiled production rules."""
    rules = list_rules(db, current_user.id, domain=domain, stage=stage, limit=limit)
    return {"ok": True, "data": [r.dict() for r in rules], "count": len(rules)}


@router.post("/productions/compile")
async def compile_productions(
    req: CompileRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compile CPG text into production rules."""
    if not req.cpg_text or not req.domain:
        raise HTTPException(status_code=400, detail="cpg_text and domain are required")

    compiler = _get_compiler()
    graph = compiler.compile(req.cpg_text, req.domain, req.source)
    rules = compile_from_cpg(db, current_user.id, graph, req.domain)

    _log_activity("compile", req.domain, f"{len(rules)} rules compiled", current_user.id)

    return {
        "ok": True,
        "data": {
            "rules": [r.dict() for r in rules],
            "graph_summary": {
                "domain": graph.domain,
                "node_count": len(graph.nodes),
                "rule_count": len(graph.rules),
                "priority_paths": len(graph.priority_paths),
            },
        },
        "count": len(rules),
    }


@router.get("/task-state")
async def get_task_state(
    session_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Get current task state (working memory) for a session."""
    tsm = _get_tsm()
    state = tsm.get_current_state(session_id)
    return {"ok": True, "data": state.dict()}


@router.post("/task-state/hypothesis")
async def update_hypothesis(
    req: HypothesisRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add, confirm, or reject a hypothesis."""
    tsm = _get_tsm()

    if req.action == "add":
        if not req.description:
            raise HTTPException(status_code=400, detail="description is required for add")
        hyp = Hypothesis(description=req.description)
        tsm.add_hypothesis(req.session_id, hyp)
        return {"ok": True, "action": "added", "hypothesis_id": hyp.id}

    elif req.action == "confirm":
        if not req.hypothesis_id:
            raise HTTPException(status_code=400, detail="hypothesis_id is required")
        tsm.confirm_hypothesis(req.session_id, req.hypothesis_id, req.evidence)
        return {"ok": True, "action": "confirmed"}

    elif req.action == "reject":
        if not req.hypothesis_id:
            raise HTTPException(status_code=400, detail="hypothesis_id is required")
        tsm.reject_hypothesis(req.session_id, req.hypothesis_id, req.evidence)
        return {"ok": True, "action": "rejected"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")


@router.delete("/task-state")
async def clear_task_state(
    session_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Close and clear task state, returning compiled DecisionGraph."""
    tsm = _get_tsm()
    graph = tsm.close_task(session_id)
    return {"ok": True, "data": graph.dict() if graph else None}


@router.patch("/productions/confidence")
async def update_rule_confidence(
    req: RuleUpdateRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Adjust a rule's confidence."""
    rule = update_confidence(db, req.rule_id, req.delta)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"ok": True, "data": rule.dict()}


@router.get("/ontology")
async def get_ontology():
    """Return the behavior ontology."""
    ba = _get_ba()
    return {"ok": True, "data": {
        "operations": list(ba.operations.keys()),
        "categories": ba.ontology.get("categories", {}),
    }}


# ── Meta Expert (Federal) Endpoints ──

from services.meta_expert import get_meta_expert, MetaExpert


class RegisterExpertRequest(BaseModel):
    domain: str
    title: str
    description: str = ""
    cpg_source: str = ""
    source_quality: str = "clinical_practice_guideline"
    agent_type: str = "contributory"  # contributory | interactional


class ConsultRequest(BaseModel):
    from_domain: str
    to_domain: str
    question: str
    urgency: str = "normal"


@router.get("/meta/philosophy")
async def get_philosophy(db: DBSession = Depends(get_db)):
    """Get the Meta-Philosophy summary."""
    meta = get_meta_expert(db)
    return {"ok": True, "data": meta.get_philosophy_summary()}


@router.get("/meta/philosophy/full")
async def get_philosophy_full():
    """Return the full meta_philosophy.json content (12 modules, 268 lines)."""
    import json as _json
    from pathlib import Path
    phil_path = Path(__file__).resolve().parent.parent / "ontology" / "meta_philosophy.json"
    if phil_path.exists():
        return {"ok": True, "data": _json.loads(phil_path.read_text(encoding="utf-8"))}
    return {"ok": True, "data": {}}


@router.get("/meta/experts")
async def list_federal_experts(db: DBSession = Depends(get_db)):
    """List all registered domain experts with Goldman trust metrics."""
    meta = get_meta_expert(db)
    return {"ok": True, "data": meta.list_experts()}


@router.post("/meta/experts/register")
async def register_federal_expert(
    req: RegisterExpertRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Register a new domain expert in the federation."""
    meta = get_meta_expert(db)
    expert = meta.register_expert(
        domain=req.domain,
        title=req.title,
        description=req.description,
        cpg_source=req.cpg_source,
        source_quality=req.source_quality,
        agent_type=req.agent_type,
    )
    return {"ok": True, "data": expert}


@router.post("/meta/consult")
async def cross_expert_consult(
    req: ConsultRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Request cross-domain expert consultation."""
    meta = get_meta_expert(db)
    result = await meta.consult(
        from_domain=req.from_domain,
        to_domain=req.to_domain,
        question=req.question,
        urgency=req.urgency,
        user_id=current_user.id,
    )
    _log_activity("consult", f"{req.from_domain}→{req.to_domain}",
                  f"urgency={req.urgency}", current_user.id)
    return {"ok": True, "data": result}


@router.get("/meta/expert/{domain}/trust")
async def get_expert_trust(
    domain: str,
    db: DBSession = Depends(get_db),
):
    """Get Goldman trust indicators for a specific expert."""
    meta = get_meta_expert(db)
    expert = meta.get_expert(domain)
    if not expert:
        raise HTTPException(status_code=404, detail=f"Expert '{domain}' not found")
    trust = meta.get_goldman_trust(domain)
    return {"ok": True, "data": {
        "domain": domain,
        "title": expert["title"],
        "agent_type": expert["agent_type"],
        **trust,
    }}


@router.post("/meta/expert/{domain}/trust/feedback")
async def update_expert_trust(
    domain: str,
    db: DBSession = Depends(get_db),
    success: bool = True,
    conflict_won: bool = False,
    peer_agreed: bool = False,
):
    """Record feedback to update Goldman trust indicators."""
    meta = get_meta_expert(db)
    if meta.get_expert(domain) is None:
        raise HTTPException(status_code=404, detail=f"Expert '{domain}' not found")
    meta.update_track_record(domain, success)
    if conflict_won:
        meta.update_dialectical_performance(domain, conflict_won)
    if peer_agreed:
        meta.update_peer_agreement(domain, "peer", True)
    return {"ok": True, "data": meta.get_goldman_trust(domain)}


# ── SME (Structure-Mapping Engine) Endpoints ──

class AnalogiesRequest(BaseModel):
    source_domain: str
    target_domains: List[str] = []


@router.post("/meta/analogies")
async def find_analogies(
    req: AnalogiesRequest,
    db: DBSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run SME MAC→FAC pipeline to discover cross-domain structural analogies."""
    from services.sme_engine import SMEEngine
    sme = SMEEngine()
    targets = req.target_domains
    if not targets:
        from services.meta_expert import get_meta_expert
        meta = get_meta_expert(db)
        experts = meta.list_experts()
        targets = [e["domain"] for e in experts if e["domain"] != req.source_domain]
    results = sme.find_analogies(
        req.source_domain, targets,
        db=db, user_id=current_user.id,
    )
    transfers = []
    for a in results:
        transfers.extend(sme.suggest_rule_transfer(a, db=db, user_id=current_user.id))
    _log_activity("analogies", req.source_domain,
                  f"{len(results)} analogies, {len(transfers)} transfers", current_user.id)
    return {"ok": True, "data": {
        "analogies": [
            {
                "source": a.source_domain,
                "target": a.target_domain,
                "similarity": a.structural_similarity,
                "shared_ops": a.shared_operations,
                "edge_type": a.edge_type,
                "transfers": a.transfer_suggestions,
            }
            for a in results
        ],
        "rule_transfers": [
            {"trigger": t.source_trigger, "target": t.target_domain,
             "rationale": t.rationale, "confidence": t.confidence}
            for t in transfers
        ],
    }}


@router.get("/meta/analogies/{domain}")
async def get_domain_links(
    domain: str,
    edge_type: str = None,
    db: DBSession = Depends(get_db),
):
    """Get cross-domain links for a domain, optionally filtered by edge type."""
    from services.sme_engine import SMEEngine
    sme = SMEEngine()
    if edge_type:
        linked = sme.query_by_edge_type(domain, edge_type)
    else:
        linked = sme.get_linked_domains(domain)
    return {"ok": True, "data": {
        "domain": domain,
        "edge_type": edge_type,
        "linked_domains": linked if isinstance(linked, list) else list(linked.keys()),
    }}


# ── Conformal Prediction Endpoints ──

class ConformalCalibrateRequest(BaseModel):
    domain: str
    alpha: float = 0.05


class ConformalPredictRequest(BaseModel):
    compiled_rule: str
    gt_candidates: List[str]
    domain: str = None
    alpha: float = 0.05


@router.post("/meta/conformal/calibrate")
async def calibrate_conformal(
    req: ConformalCalibrateRequest,
):
    """Calibrate conformal predictor for a domain. Returns q_hat threshold."""
    from services.conformal_predictor import ConformalPredictor
    cp = ConformalPredictor(alpha=req.alpha)
    result = cp.calibrate(req.domain, req.alpha)
    return {"ok": True, "data": {
        "domain": result.domain,
        "alpha": result.alpha,
        "q_hat": result.q_hat,
        "n_calibration": result.n_calibration,
        "coverage_guarantee": result.coverage_guarantee,
        "calibrated_at": result.calibrated_at,
    }}


@router.post("/meta/conformal/predict")
async def predict_conformal(
    req: ConformalPredictRequest,
):
    """Generate conformal prediction set for a compiled rule."""
    from services.conformal_predictor import ConformalPredictor
    cp = ConformalPredictor(alpha=req.alpha)
    results = cp.predict(
        req.compiled_rule, req.gt_candidates,
        domain=req.domain, alpha=req.alpha,
    )
    return {"ok": True, "data": [
        {
            "rule": r.rule_text,
            "included": r.included,
            "nonconformity": r.nonconformity,
            "threshold": r.threshold,
            "confidence_text": r.confidence_text,
        }
        for r in results
    ]}


@router.get("/meta/conformal/coverage/{domain}")
async def evaluate_conformal_coverage(
    domain: str,
    alpha: float = 0.05,
    db: DBSession = Depends(get_db),
):
    """Evaluate empirical coverage of conformal predictor on domain test pairs."""
    from services.conformal_predictor import ConformalPredictor, _load_calibration_pairs
    cp = ConformalPredictor(alpha=alpha)
    test_pairs = _load_calibration_pairs(domain)
    if not test_pairs:
        return {"ok": True, "data": {"detail": "No test pairs available for this domain"}}
    report = cp.evaluate_coverage(test_pairs, domain, alpha)
    return {"ok": True, "data": {
        "domain": report.domain,
        "alpha": report.alpha,
        "empirical_coverage": report.empirical_coverage,
        "n_test": report.n_test,
        "meets_guarantee": report.meets_guarantee,
        "detail": report.detail,
    }}


# ── Feedback ──

class FeedbackRequest(BaseModel):
    log_id: int
    signal: str  # "positive" or "negative"
    comment: Optional[str] = None


@router.post("/feedback")
def submit_feedback(
    req: FeedbackRequest,
    db: DBSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Record user feedback on an expert inference.

    signal: 'positive' (diagnosis was helpful) or 'negative' (diagnosis was wrong)
    Updates rule confidence and feeds JEPA training data.
    """
    if req.signal not in ("positive", "negative"):
        raise HTTPException(status_code=400, detail="signal must be 'positive' or 'negative'")

    from models.inference_log import InferenceLog
    from datetime import datetime, timezone

    log = db.query(InferenceLog).filter(
        InferenceLog.id == req.log_id,
        InferenceLog.user_id == current_user.id,
    ).first()

    if not log:
        raise HTTPException(status_code=404, detail="Inference log not found")

    log.user_signal = req.signal
    log.feedback_at = datetime.now(timezone.utc)
    db.commit()

    # Update rule confidence based on feedback
    if log.rule_ids:
        from services.production_store import update_confidence
        delta = +1 if req.signal == "positive" else -1
        try:
            for rid in log.rule_ids:
                update_confidence(db, rid, delta, req.signal)
        except Exception:
            db.rollback()

    logger.info(f"Expert feedback: log={req.log_id} signal={req.signal} user={current_user.id}")

    return {
        "ok": True,
        "message": "感谢反馈！" if req.signal == "positive" else "已记录，我们会改进。",
    }
