"""Autopilot Service — combines Policy Engine + Executor + Decision Logger.
Provides preflight() and postflight() as the two main entry points."""
import time
from typing import Any, Dict, Optional

from services.autopilot.schemas import PolicyInput
from services.autopilot.memory_policy import decide_policy
from services.autopilot.memory_executor import execute_all
from services.autopilot import decision_logger

def preflight(user_message, project_id=None, agent=None, headers=None, user_id="unknown"):
    # type: (str, Optional[str], Optional[str], Optional[Dict[str, str]], str) -> Dict[str, Any]
    """Pre-turn: decide what memory to read before answering.
    Returns memory_context and decision log."""
    hdrs = headers or {}

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
    result = execute_all(policy, user_id, auth_headers=hdrs)

    # Step 3: log decision
    log_entry = {
        "user_id": user_id,
        "phase": "pre_turn",
        "user_message_chars": len(user_message),
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


def postflight(user_message, assistant_response, project_id=None, agent=None, headers=None, user_id="unknown"):
    # type: (str, str, Optional[str], Optional[str], Optional[Dict[str, str]], str) -> Dict[str, Any]
    """Post-turn: decide what to write/capture/update after answering.
    Creates inbox/counter/review items. Never writes directly to memory."""
    hdrs = headers or {}

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
    result = execute_all(policy, user_id, auth_headers=hdrs)

    # Step 3: log decision
    log_entry = {
        "user_id": user_id,
        "phase": "post_turn",
        "user_message_chars": len(user_message),
        "assistant_response_chars": len(assistant_response),
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
