"""Lifecycle Auto-Scanner — background scheduler for periodic memory health checks.

Runs full lifecycle scan for all users on a configurable interval.
Findings go to inbox automatically with source='auto-scan' tag.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from config import SessionLocal
from services.lifecycle_scanner import run_full_scan, findings_to_inbox_items
from models.inbox import InboxItem

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "auto_scan_config.json"
DEFAULT_INTERVAL_HOURS = 24

# ── In-memory state ──
_state: Dict = {
    "enabled": True,
    "interval_hours": DEFAULT_INTERVAL_HOURS,
    "last_scan_at": None,       # ISO string
    "last_scan_findings": 0,
    "next_scan_at": None,       # ISO string
    "scanned_users": 0,
}

_scheduler: Optional[BackgroundScheduler] = None


def _load_config():
    """Load persisted config from disk."""
    global _state
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _state.update(saved)
        except Exception as e:
            logger.warning(f"Auto-scan config load failed: {e}")


def _save_config():
    """Persist config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(_state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_state() -> Dict:
    """Return current auto-scan state."""
    return {
        "enabled": _state["enabled"],
        "interval_hours": _state["interval_hours"],
        "last_scan_at": _state["last_scan_at"],
        "last_scan_findings": _state["last_scan_findings"],
        "next_scan_at": _state["next_scan_at"],
        "scanned_users": _state["scanned_users"],
    }


def set_enabled(enabled: bool) -> Dict:
    """Enable or disable auto-scan. Returns updated state."""
    _state["enabled"] = enabled
    _save_config()
    logger.info(f"Auto-scan {'enabled' if enabled else 'disabled'}")
    return get_state()


def set_interval(hours: int) -> Dict:
    """Change scan interval. Reschedules the job."""
    hours = max(1, min(168, hours))  # clamp: 1h ~ 7d
    _state["interval_hours"] = hours
    _save_config()
    _reschedule(hours)
    logger.info(f"Auto-scan interval changed to {hours}h")
    return get_state()


def _do_scan():
    """Execute one full scan cycle for all users."""
    if not _state["enabled"]:
        logger.info("Auto-scan skipped (disabled)")
        return

    db = SessionLocal()
    try:
        from models.context_object import ContextObject
        from sqlalchemy import distinct, and_

        # Find all users with enough context objects (≥5)
        user_ids = [
            row[0] for row in
            db.query(distinct(ContextObject.user_id)).filter(
                ContextObject.type != "rule"
            ).all()
        ]

        total_findings = 0
        scanned = 0
        now = datetime.now(timezone.utc)

        for uid in user_ids:
            count = db.query(ContextObject).filter(
                ContextObject.user_id == uid,
                ContextObject.type != "rule",
            ).count()

            if count < 5:
                continue

            try:
                findings = run_full_scan(db, uid)
                items = findings_to_inbox_items(findings, uid)

                for item in items:
                    # Tag as auto-scan so user can distinguish from manual scans
                    existing_tags = item.get("tags", "")
                    if isinstance(existing_tags, list):
                        item["tags"] = existing_tags + ["auto-scan"]
                    else:
                        item["tags"] = "lifecycle,auto-scan"

                    db.add(InboxItem(**item))
                    total_findings += 1

                scanned += 1
            except Exception as e:
                logger.error(f"Auto-scan failed for user {uid}: {e}")
                continue

        db.commit()

        _state["last_scan_at"] = now.isoformat()
        _state["last_scan_findings"] = total_findings
        _state["scanned_users"] = scanned
        _save_config()

        logger.info(
            f"Auto-scan complete: {scanned} users, {total_findings} findings → inbox"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Auto-scan cycle failed: {e}")
    finally:
        db.close()


def _reschedule(hours: int):
    """Reschedule the scan job with new interval."""
    global _scheduler
    if _scheduler is None:
        return

    job_id = "lifecycle_auto_scan"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    _scheduler.add_job(
        _do_scan,
        trigger="interval",
        hours=hours,
        id=job_id,
        name="Lifecycle Auto-Scan",
        replace_existing=True,
        next_run_time=None,  # start after first interval
    )

    # Update next scan time
    from datetime import timedelta
    next_run = datetime.now(timezone.utc) + timedelta(hours=hours)
    _state["next_scan_at"] = next_run.isoformat()
    _save_config()


def start_scheduler():
    """Start the background scheduler. Called once on app startup."""
    global _scheduler
    if _scheduler is not None:
        return

    _load_config()

    _scheduler = BackgroundScheduler(
        daemon=True,
        timezone="Asia/Shanghai",
    )

    interval = _state.get("interval_hours", DEFAULT_INTERVAL_HOURS)

    _scheduler.add_job(
        _do_scan,
        trigger="interval",
        hours=interval,
        id="lifecycle_auto_scan",
        name="Lifecycle Auto-Scan",
        replace_existing=True,
        # Run first scan after 5 minutes to avoid blocking startup
        next_run_time=None,
    )

    _scheduler.start()
    logger.info(f"Auto-scan scheduler started (interval={interval}h)")

    # Schedule first scan 5 min after startup
    from datetime import timedelta
    next_run = datetime.now(timezone.utc) + timedelta(minutes=5)
    _state["next_scan_at"] = next_run.isoformat()
    _save_config()


def stop_scheduler():
    """Stop the background scheduler. Called on app shutdown."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Auto-scan scheduler stopped")
