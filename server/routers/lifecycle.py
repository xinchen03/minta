"""Lifecycle API — trigger memory health scans. Findings go to inbox."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user
from models.inbox import InboxItem
from models.context_object import ContextObject
from services.lifecycle_scanner import run_full_scan, findings_to_inbox_items
from services.lifecycle_auto_scanner import get_state, set_enabled, set_interval
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])


@router.post("/scan")
def trigger_scan(
    write_to_inbox: bool = True,
    db: DBSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Run a lifecycle scan for the current user. Findings go to inbox.

    Set write_to_inbox=false to dry-run (return findings without writing).
    """
    uid = user.id

    total = db.query(ContextObject).filter(
        ContextObject.user_id == uid,
        ContextObject.type != "rule",
    ).count()

    if total < 5:
        return {
            "ok": True,
            "scanned": False,
            "reason": f"Only {total} contexts. Scan requires at least 5.",
            "findings": {"staleness": [], "redundancy": [], "fragmentation": [], "conflict": []},
            "inbox_written": 0,
        }

    findings = run_full_scan(db, uid)

    inbox_count = 0
    if write_to_inbox:
        items = findings_to_inbox_items(findings, uid)
        for item in items:
            db.add(InboxItem(**item))
            inbox_count += 1
        db.commit()

    return {
        "ok": True,
        "scanned": True,
        "total_contexts": total,
        "findings": {
            "staleness": len(findings["staleness"]),
            "redundancy": len(findings["redundancy"]),
            "fragmentation": len(findings["fragmentation"]),
            "conflict": len(findings["conflict"]),
        },
        "details": {
            k: [{"title": f["title"] if "title" in f else f.get("titles", []),
                 "suggestion": f["suggestion"]}
                for f in v[:5]]
            for k, v in findings.items() if v
        },
        "inbox_written": inbox_count,
    }


@router.get("/stats")
def lifecycle_stats(
    db: DBSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Quick stats about memory health without a full scan."""
    uid = user.id
    total = db.query(ContextObject).filter(ContextObject.user_id == uid).count()
    active = db.query(ContextObject).filter(
        ContextObject.user_id == uid, ContextObject.status == "active"
    ).count()
    stale = db.query(ContextObject).filter(
        ContextObject.user_id == uid, ContextObject.status == "stale"
    ).count()
    rules = db.query(ContextObject).filter(
        ContextObject.user_id.in_([uid, 0]), ContextObject.type == "rule"
    ).count()

    # Inbox pending
    pending = db.query(InboxItem).filter(
        InboxItem.user_id == uid, InboxItem.status == "pending",
        InboxItem.tags.contains("lifecycle"),
    ).count()

    return {
        "ok": True,
        "total_contexts": total,
        "active": active,
        "stale": stale,
        "expert_rules": rules,
        "pending_lifecycle_items": pending,
    }


# ── Auto-Scan endpoints ──

@router.get("/auto-scan/status")
def auto_scan_status(
    user = Depends(get_current_user),
):
    """Get auto-scan configuration and last run info."""
    return {"ok": True, **get_state()}


@router.post("/auto-scan/toggle")
def auto_scan_toggle(
    enabled: bool = Query(..., description="Enable or disable auto-scan"),
    user = Depends(get_current_user),
):
    """Enable or disable the automatic lifecycle scan scheduler."""
    return {"ok": True, **set_enabled(enabled)}


@router.post("/auto-scan/interval")
def auto_scan_interval(
    hours: int = Query(..., ge=1, le=168, description="Scan interval in hours (1–168)"),
    user = Depends(get_current_user),
):
    """Change the auto-scan interval (1 hour to 7 days)."""
    return {"ok": True, **set_interval(hours)}
