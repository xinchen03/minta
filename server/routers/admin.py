"""Admin router — user management, system stats, experiment dashboard."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from config import get_db
from routers.auth import get_current_user, User
from models.context_object import ContextObject
from models.inbox import InboxItem

router = APIRouter(prefix="/api/admin", tags=["admin"])


import os
ADMIN_IDS = {int(x) for x in os.environ.get("MINTA_ADMIN_IDS", "").split(",") if x.strip()}


def require_admin(user: User = Depends(get_current_user)):
    """Admin check: set MINTA_ADMIN_IDS=1,2,3 in .env to grant admin."""
    if not ADMIN_IDS or user.id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/stats")
def get_stats(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """System-wide statistics."""
    # User stats
    from routers.auth import User as UserModel
    total_users = db.query(func.count(UserModel.id)).scalar()
    users_registered_today = db.query(func.count(UserModel.id)).filter(
        func.date(UserModel.created_at) == func.current_date()
    ).scalar()

    # Context stats
    total_contexts = db.query(func.count(ContextObject.id)).scalar()
    context_by_user = db.query(
        ContextObject.user_id, func.count(ContextObject.id)
    ).group_by(ContextObject.user_id).all()

    # Inbox stats
    total_inbox = db.query(func.count(InboxItem.id)).scalar()
    pending_inbox = db.query(func.count(InboxItem.id)).filter(
        InboxItem.status == "pending"
    ).scalar()

    return {
        "users": {"total": total_users, "registeredToday": users_registered_today},
        "contexts": {"total": total_contexts},
        "inbox": {"total": total_inbox, "pending": pending_inbox},
    }


@router.get("/users")
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all users with their stats."""
    from routers.auth import User as UserModel
    users = db.query(UserModel).order_by(UserModel.created_at.desc()).all()
    result = []
    for u in users:
        ctx_count = db.query(func.count(ContextObject.id)).filter(
            ContextObject.user_id == u.id
        ).scalar()
        inbox_count = db.query(func.count(InboxItem.id)).filter(
            InboxItem.user_id == u.id, InboxItem.status == "pending"
        ).scalar()
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "emailVerified": u.email_verified,
            "createdAt": str(u.created_at) if u.created_at else "",
            "avatarUrl": u.avatar_url,
            "contextCount": ctx_count,
            "pendingInbox": inbox_count,
        })
    return result


# ── Experiment Dashboard ──

@router.get("/experiment/retrieval-stats")
def retrieval_stats(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Retrieval counts by policy (BM25 vs PCL-Bandit) over time."""
    rows = db.execute(text("""
        SELECT
            DATE(created_at) AS day,
            policy,
            COUNT(*) AS retrievals,
            COUNT(DISTINCT user_id) AS active_users,
            AVG(k_shown) AS avg_k_shown
        FROM context_retrieval_log
        GROUP BY DATE(created_at), policy
        ORDER BY day, policy
    """)).all()
    return [{"day": str(r[0]), "policy": r[1], "retrievals": r[2], "activeUsers": r[3], "avgKShown": float(r[4])} for r in rows]


@router.get("/experiment/reward-trend")
def reward_trend(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Reward signals over time by experiment condition."""
    rows = db.execute(text("""
        SELECT
            DATE(t.created_at) AS day,
            u.experiment_condition AS exp_cond,
            COUNT(*) AS tasks,
            AVG(t.iteration_count) AS avg_iterations,
            AVG(t.direct_copy) AS avg_direct_copy,
            AVG(t.quality_rating) AS avg_quality,
            AVG(t.composite_reward) AS avg_reward
        FROM task_reward_log t
        JOIN users u ON t.user_id = u.id
        GROUP BY DATE(t.created_at), u.experiment_condition
        ORDER BY day, exp_cond
    """)).all()
    return [{
        "day": str(r[0]), "condition": r[1], "tasks": r[2],
        "avgIterations": float(r[3]) if r[3] else 0,
        "avgDirectCopy": float(r[4]) if r[4] else 0,
        "avgQuality": float(r[5]) if r[5] else None,
        "avgReward": float(r[6]) if r[6] else 0,
    } for r in rows]  # condition = exp_cond (u.experiment_condition)


@router.get("/experiment/group-comparison")
def group_comparison(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Aggregate comparison between control and treatment groups."""
    rows = db.execute(text("""
        SELECT
            u.experiment_condition,
            COUNT(DISTINCT t.user_id) AS user_count,
            COUNT(*) AS task_count,
            AVG(t.composite_reward) AS avg_reward,
            AVG(t.iteration_count) AS avg_iterations,
            AVG(t.direct_copy) AS avg_direct_copy,
            AVG(t.quality_rating) AS avg_quality,
            AVG(t.context_count) AS avg_context_count
        FROM task_reward_log t
        JOIN users u ON t.user_id = u.id
        WHERE u.experiment_condition IS NOT NULL
        GROUP BY u.experiment_condition
    """)).all()
    return [{
        "condition": r[0], "userCount": r[1], "taskCount": r[2],
        "avgReward": float(r[3]) if r[3] else 0,
        "avgIterations": float(r[4]) if r[4] else 0,
        "avgDirectCopy": float(r[5]) if r[5] else 0,
        "avgQuality": float(r[6]) if r[6] else None,
        "avgContextCount": float(r[7]) if r[7] else 0,
    } for r in rows]


@router.get("/experiment/bandit-convergence")
def bandit_convergence(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Bandit state summary — arms trained, pulls distribution."""
    rows = db.execute(text("""
        SELECT
            user_id,
            COUNT(*) AS arms,
            SUM(pulled_count) AS total_pulls,
            AVG(pulled_count) AS avg_pulls,
            MAX(pulled_count) AS max_pulls
        FROM bandit_state
        GROUP BY user_id
        ORDER BY total_pulls DESC
    """)).all()
    return [{
        "userId": r[0], "arms": r[1], "totalPulls": r[2],
        "avgPulls": float(r[3]) if r[3] else 0,
        "maxPulls": r[4],
    } for r in rows]


@router.get("/experiment/summary")
def experiment_summary(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Overall experiment snapshot."""
    # Total retrievals logged
    total_retrievals = db.execute(text("SELECT COUNT(*) FROM context_retrieval_log")).scalar()
    total_rewards = db.execute(text("SELECT COUNT(*) FROM task_reward_log")).scalar()
    total_bandit_arms = db.execute(text("SELECT COUNT(*) FROM bandit_state")).scalar()

    # User distribution
    rows = db.execute(text("""
        SELECT experiment_condition, COUNT(*) FROM users
        WHERE experiment_condition IS NOT NULL
        GROUP BY experiment_condition
    """)).all()
    user_dist = {r[0]: r[1] for r in rows}

    # Date range
    first_log = db.execute(text("SELECT MIN(created_at) FROM context_retrieval_log")).scalar()
    last_log = db.execute(text("SELECT MAX(created_at) FROM context_retrieval_log")).scalar()

    return {
        "totalRetrievals": total_retrievals or 0,
        "totalRewards": total_rewards or 0,
        "totalBanditArms": total_bandit_arms or 0,
        "userDistribution": user_dist,
        "dateRange": {"first": str(first_log) if first_log else None, "last": str(last_log) if last_log else None},
    }
