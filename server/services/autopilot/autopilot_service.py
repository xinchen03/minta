"""Autopilot Service — combines Policy Engine + Executor + Decision Logger.
Provides preflight() and postflight() as the two main entry points."""
import os
import time
from typing import Any, Dict, Optional

from services.autopilot.schemas import PolicyInput
from services.autopilot.memory_policy import decide_policy
from services.autopilot.memory_executor import execute_all
from services.autopilot import decision_logger

try:
    from config import MINTA_API_KEY as CONFIG_API_KEY
    API_KEY = os.environ.get("MINTA_API_KEY", "") or CONFIG_API_KEY
except ImportError:
    API_KEY = os.environ.get("MINTA_API_KEY", "")


def _resolve_user_id(headers=None):
    # type: (Optional[Dict[str, str]]) -> str
    """Resolve user_id from API key or headers.
    Falls back to 'unknown' if not resolvable."""
    key = API_KEY or (headers or {}).get("x-api-key", "")
    if key:
        # Try to resolve via API
        import urllib.request
        import json

        try:
            api_url = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
            req = urllib.request.Request(
                "%s/api/auth/me" % api_url,
                headers={"X-API-Key": key},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return str(data.get("id", "unknown"))
        except Exception:
            pass
    return "unknown"


def preflight(user_message, project_id=None, agent=None, headers=None):
    # type: (str, Optional[str], Optional[str], Optional[Dict[str, str]]) -> Dict[str, Any]
    """Pre-turn: decide what memory to read before answering.
    Returns memory_context and decision log."""
    user_id = _resolve_user_id(headers)
    hdrs = headers or {}
    api_key = hdrs.get("x-api-key", "") or hdrs.get("X-API-Key", "") or hdrs.get("X-Api-Key", "")

    inp = PolicyInput(
        user_id=user_id,
        phase="pre_turn",
        user_message=user_message,
        project_id=project_id,
        agent=agent,
    )

    # Step 1: decide policy
    policy = decide_policy(inp)

    # Step 2: execute (read only) with API key from headers
    result = execute_all(policy, user_id, api_key_override=api_key)

    # Step 3: log decision
    log_entry = {
        "user_id": user_id,
        "phase": "pre_turn",
        "user_message_excerpt": user_message[:200],
        "project_id": project_id,
        "agent": agent,
        "decision": {
            "read": {
                "should_run": policy.read.should_run,
                "confidence": policy.read.confidence,
                "reason": policy.read.reason,
            }
        },
        "executed": {
            "read_performed": result["read"]["read_performed"],
            "memory_context_keys": list(result["read"].get("memory_context", {}).keys()),
        },
        "status": "executed",
    }
    log_id = decision_logger.write_log(log_entry)

    return {
        "read_triggered": policy.read.should_run,
        "reason": policy.read.reason,
        "memory_context": result["read"].get("memory_context", {}),
        "log_id": log_id,
        "degraded": False,
    }


def postflight(user_message, assistant_response, project_id=None, agent=None, headers=None):
    # type: (str, str, Optional[str], Optional[str], Optional[Dict[str, str]]) -> Dict[str, Any]
    """Post-turn: decide what to write/capture/update after answering.
    Creates inbox/counter/review items. Never writes directly to memory."""
    user_id = _resolve_user_id(headers)
    hdrs = headers or {}
    api_key = hdrs.get("x-api-key", "") or hdrs.get("X-API-Key", "") or hdrs.get("X-Api-Key", "")

    inp = PolicyInput(
        user_id=user_id,
        phase="post_turn",
        user_message=user_message,
        assistant_response=assistant_response,
        project_id=project_id,
        agent=agent,
    )

    # Step 1: decide policy
    policy = decide_policy(inp)

    # Step 2: execute (write/counter/update only) with API key from headers
    result = execute_all(policy, user_id, api_key_override=api_key)

    # Step 3: log decision
    log_entry = {
        "user_id": user_id,
        "phase": "post_turn",
        "user_message_excerpt": user_message[:200],
        "assistant_response_excerpt": assistant_response[:200],
        "project_id": project_id,
        "agent": agent,
        "decision": {
            "write": {
                "should_run": policy.write.should_run,
                "confidence": policy.write.confidence,
                "reason": policy.write.reason,
            },
            "counter_capture": {
                "should_run": policy.counter_capture.should_run,
                "confidence": policy.counter_capture.confidence,
                "reason": policy.counter_capture.reason,
            },
            "update": {
                "should_run": policy.update.should_run,
                "confidence": policy.update.confidence,
                "reason": policy.update.reason,
            },
        },
        "executed": {
            "writes_created": result["write"]["writes_created"],
            "inbox_ids": result["write"]["inbox_ids"],
            "counter_created": result["counter_capture"]["counter_created"],
            "counter_ids": result["counter_capture"]["counter_ids"],
            "updates_created": result["update"]["updates_created"],
            "review_ids": result["update"]["review_ids"],
        },
        "summary": result.get("summary", {}),
        "status": "executed",
    }
    log_id = decision_logger.write_log(log_entry)

    return {
        "write_triggered": policy.write.should_run,
        "counter_capture_triggered": policy.counter_capture.should_run,
        "update_triggered": policy.update.should_run,
        "created": {
            "inbox_items": result["write"]["inbox_ids"],
            "counter_items": result["counter_capture"]["counter_ids"],
            "review_items": result["update"]["review_ids"],
        },
        "reason": _build_post_reason(policy),
        "log_id": log_id,
        "degraded": False,
    }


def _build_post_reason(policy):
    # type: (Any) -> str
    """Build a human-readable reason string from post-turn policy decisions."""
    parts = []
    if policy.write.should_run:
        parts.append("write:%s" % policy.write.reason)
    if policy.counter_capture.should_run:
        parts.append("counter:%s" % policy.counter_capture.reason)
    if policy.update.should_run:
        parts.append("update:%s" % policy.update.reason)
    return "; ".join(parts) if parts else "no action triggered"
