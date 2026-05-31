"""Experiment data collection — retrieval logs, reward signals, bandit selection."""
import json
import random
import numpy as np
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from config import get_db
from routers.auth import get_current_user, User
from models.context_retrieval_log import ContextRetrievalLog
from models.task_reward_log import TaskRewardLog
from models.bandit_state import BanditState
from models.graph_edge import GraphEdge

# Optional: log user activity for engagement analysis
_ACTIVITY_LOG = []  # keep last 1000 in memory, flushed to db periodically

from models.activity_log import ActivityLog

router = APIRouter(prefix="/api/experiment", tags=["experiment"])

_SESSION_COUNTER: dict = {}


def _session_id(user_id: int, prefix: str = "exp") -> str:
    _SESSION_COUNTER[user_id] = _SESSION_COUNTER.get(user_id, 0) + 1
    return f"{prefix}-{user_id}-{_SESSION_COUNTER[user_id]}-{int(datetime.utcnow().timestamp())}"


def _composite_reward(iteration_count: int, direct_copy: bool, quality_rating: float = None) -> float:
    """Calculate composite reward from task signals."""
    iter_score = max(0, 1 - (iteration_count - 1) * 0.2)
    copy_score = 0.4 if direct_copy else 0
    quality_score = ((quality_rating or 3) / 5) * 0.3
    return round(iter_score + copy_score + quality_score, 4)


@router.post("/log-retrieval")
def log_retrieval(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log a context retrieval event. Called whenever contexts are ranked/selected for a user."""
    session_id = payload.get("sessionId", f"session-{user.id}-{int(datetime.utcnow().timestamp())}")
    task_embedding = payload.get("taskEmbedding")  # optional 32d PCA embedding
    ranked_ids = payload.get("rankedContextIds", [])
    scores = payload.get("scores", [])
    k_shown = payload.get("kShown", len(ranked_ids))
    context_count = payload.get("contextCount", 0)
    policy = payload.get("policy", "bm25")  # "bm25" | "pcl_bandit"

    log = ContextRetrievalLog(
        user_id=user.id,
        session_id=session_id,
        task_embedding=json.dumps(task_embedding) if task_embedding else None,
        ranked_context_ids=json.dumps(ranked_ids),
        scores=json.dumps(scores),
        k_shown=k_shown,
        exp_condition=user.experiment_condition or "control",
        context_count=context_count,
        policy=policy,
    )
    db.add(log)
    db.commit()
    return {"success": True, "id": log.id}


@router.post("/log-reward")
def log_reward(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log a task reward signal. Called when a user completes a task."""
    session_id = payload.get("sessionId", f"reward-{user.id}-{int(datetime.utcnow().timestamp())}")
    context_count = payload.get("contextCount", 0)
    iteration_count = payload.get("iterationCount", 1)
    direct_copy = payload.get("directCopy", 0)
    quality_rating = payload.get("qualityRating")

    composite_reward = _composite_reward(iteration_count, bool(direct_copy), quality_rating)

    log = TaskRewardLog(
        user_id=user.id,
        session_id=session_id,
        exp_condition=user.experiment_condition or "control",
        context_count=context_count,
        iteration_count=iteration_count,
        direct_copy=1 if direct_copy else 0,
        quality_rating=quality_rating,
        composite_reward=composite_reward,
    )
    db.add(log)
    db.commit()
    return {"success": True, "id": log.id, "compositeReward": composite_reward}


def _log_activity(db: Session, user_id: int, event_type: str, detail: str = None):
    """Write an activity event. Non-blocking, best-effort."""
    try:
        log = ActivityLog(user_id=user_id, event_type=event_type, detail=detail)
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


@router.post("/log-activity")
def log_activity(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Log a user activity event for engagement analysis."""
    _log_activity(db, user.id, payload.get("eventType", "unknown"), payload.get("detail"))
    return {"success": True}

# ── Simple LinUCB Bandit ──

@router.get("/select")
def select_contexts(
    k: int = 3,
    task_embedding: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """PCL-Bandit selection: choose k contexts for the current task.
    Uses LinUCB with fallback to BM25 for cold-start arms.
    Returns ranked context IDs with scores.
    """
    from models.context_object import ContextObject

    # Get user's active contexts
    contexts = db.query(ContextObject).filter(
        ContextObject.user_id == user.id,
        ContextObject.status == "active",
    ).all()

    if not contexts:
        return {"contexts": [], "policy": "none", "reason": "no contexts"}

    context_ids = [c.id for c in contexts]
    context_count = len(context_ids)

    # Check if we have bandit state for any of these
    bandit_arms = db.query(BanditState).filter(
        BanditState.user_id == user.id,
        BanditState.context_id.in_(context_ids),
    ).all()
    trained_ids = {a.context_id for a in bandit_arms}

    if len(trained_ids) < 3:
        # Cold start: BM25 fallback + random exploration
        policy = "bm25"
        # Score by recency (newer = higher) mixed with randomness
        scores = []
        for i, ctx in enumerate(contexts):
            base_score = 1.0 - (i / len(contexts)) * 0.3  # newer first
            if ctx.id in trained_ids:
                arm = [a for a in bandit_arms if a.context_id == ctx.id][0]
                # Use existing bandit arms for part of the score
                try:
                    b = json.loads(arm.b_json)
                    base_score += sum(b) / len(b) * 0.5
                except (json.JSONDecodeError, ZeroDivisionError):
                    pass
            else:
                # Graph-based cold start: look for similar trained arms
                similar = db.query(GraphEdge).filter(
                    GraphEdge.user_id == user.id,
                    GraphEdge.context_id_a == ctx.id,
                    GraphEdge.context_id_b.in_(trained_ids),
                ).order_by(GraphEdge.weight.desc()).first()
                if similar:
                    base_score += similar.weight * 0.3
            noise = random.uniform(0, 0.1)
            scores.append((ctx.id, base_score + noise))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_k = scores[:min(k, len(scores))]

        # Log the retrieval
        session_id = f"bm25-{user.id}-{int(datetime.utcnow().timestamp())}"
        log = ContextRetrievalLog(
            user_id=user.id, session_id=session_id,
            ranked_context_ids=json.dumps([s[0] for s in top_k]),
            scores=json.dumps([round(s[1], 4) for s in top_k]),
            k_shown=len(top_k), exp_condition=user.experiment_condition or "control",
            context_count=context_count, policy="bm25",
        )
        db.add(log)
        db.commit()

        return {
            "contexts": [{"id": s[0], "score": round(s[1], 4)} for s in top_k],
            "policy": "bm25",
            "totalContexts": context_count,
        }

    # LinUCB selection
    policy = "pcl_bandit"
    scores = []
    for arm in bandit_arms:
        try:
            A = np.array(json.loads(arm.A_json), dtype=float)
            b_val = np.array(json.loads(arm.b_json), dtype=float)
            A_inv = np.linalg.inv(A)
            theta = A_inv @ b_val
            x = np.ones(5) / np.sqrt(5)  # unit context vector
            ucb = theta @ x + 0.2 * np.sqrt(x @ A_inv @ x)
            scores.append((arm.context_id, float(ucb)))
        except Exception:
            scores.append((arm.context_id, random.random()))

    scores.sort(key=lambda x: x[1], reverse=True)
    top_k = scores[:min(k, len(scores))]

    # Log
    session_id = f"pcl-{user.id}-{int(datetime.utcnow().timestamp())}"
    log = ContextRetrievalLog(
        user_id=user.id, session_id=session_id,
        ranked_context_ids=json.dumps([s[0] for s in top_k]),
        scores=json.dumps([round(s[1], 4) for s in top_k]),
        k_shown=len(top_k), exp_condition=user.experiment_condition or "control",
        context_count=context_count, policy="pcl_bandit",
    )
    db.add(log)
    db.commit()

    return {
        "contexts": [{"id": s[0], "score": round(s[1], 4)} for s in top_k],
        "policy": "pcl_bandit",
        "totalContexts": context_count,
    }
