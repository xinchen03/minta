"""Memory Executor — maps policy decisions to Minta API calls.
Side-effect layer: reads/writes via existing Minta API.
Zero direct DB access — all operations go through HTTP to the Minta API."""
import json
import os
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from services.autopilot.schemas import (
    PolicyResult,
    Decision,
)

MINTA_API = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")

# Try config module first (in-process), then env var
try:
    from config import MINTA_API_KEY as _CONFIG_KEY
    _ENV_KEY = os.environ.get("MINTA_API_KEY", "") or _CONFIG_KEY
except ImportError:
    _ENV_KEY = os.environ.get("MINTA_API_KEY", "")


import logging

_AUTOPILOT_LOG = logging.getLogger("minta.autopilot")


def _api_key(override=None):
    # type: (Optional[str]) -> str
    """Get API key: override > env var/config > empty."""
    key = override or _ENV_KEY or ""
    if not key:
        _AUTOPILOT_LOG.warning("No API key available for autopilot executor")
    return key


# ── HTTP helpers ──


def _headers(key_override=None):
    """Build auth headers using API key."""
    h = {"Content-Type": "application/json"}
    k = _api_key(key_override)
    if k:
        h["X-API-Key"] = k
    return h


def _api_get(path, api_key_override=None):
    # type: (str, Optional[str]) -> Optional[Dict[str, Any]]
    """GET request to Minta API."""
    try:
        req = urllib.request.Request(
            "%s%s" % (MINTA_API, path),
            headers=_headers(api_key_override),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _api_post(path, body, api_key_override=None):
    # type: (str, dict, Optional[str]) -> Optional[Dict[str, Any]]
    """POST request to Minta API."""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "%s%s" % (MINTA_API, path),
            data=data,
            headers=_headers(api_key_override),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _AUTOPILOT_LOG.error("API POST %s failed: HTTP %s: %s", path, e.code, e.read().decode())
        return None
    except Exception as e:
        _AUTOPILOT_LOG.error("API POST %s failed: %s", path, e)
        return None


# ── Read execution ──


def execute_read(policy_result, user_id, api_key_override=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute read decisions from policy result.
    Reads memory context from existing Minta APIs.
    Returns structured memory_context dict."""
    read_dec = policy_result.read
    if not read_dec.should_run:
        return {"read_performed": False, "memory_context": {}}

    queries = []
    if read_dec.payload and "queries" in read_dec.payload:
        queries = read_dec.payload["queries"]

    memory_context = {
        "user_preferences": [],
        "project_context": [],
        "counterexamples": [],
        "expert_findings": [],
        "skills": [],
    }

    key = api_key_override

    # Read user preferences and project context from contextObjects
    context_objects = _api_get("/api/contextObjects", key)
    if context_objects and isinstance(context_objects, list):
        for obj in context_objects:
            obj_type = obj.get("type", "")
            if obj_type in ("preference",) and len(memory_context["user_preferences"]) < 10:
                memory_context["user_preferences"].append({
                    "id": obj.get("id"),
                    "title": obj.get("title"),
                    "summary": obj.get("summary", ""),
                })
            elif obj_type in ("project_context", "decision_criteria") and len(memory_context["project_context"]) < 10:
                memory_context["project_context"].append({
                    "id": obj.get("id"),
                    "title": obj.get("title"),
                    "summary": obj.get("summary", ""),
                })

    # Read counterexamples from inbox
    inbox = _api_get("/api/inbox", key)
    if inbox and isinstance(inbox, dict):
        archived = inbox.get("archived", [])
        for item in archived[:10]:
            memory_context["counterexamples"].append({
                "title": item.get("title", ""),
                "body": item.get("body", ""),
            })

    # Read skills
    skills = _api_get("/api/skills", key)
    if skills and isinstance(skills, list):
        memory_context["skills"] = [
            {"name": s.get("name"), "group": s.get("group")}
            for s in skills[:10]
        ]

    return {
        "read_performed": True,
        "reason": read_dec.reason,
        "confidence": read_dec.confidence,
        "memory_context": memory_context,
    }


# ── Write execution ──


def execute_write(policy_result, user_id, api_key_override=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute write decisions. Creates inbox items for user review."""
    write_dec = policy_result.write
    if not write_dec.should_run:
        return {"writes_created": 0, "inbox_ids": []}

    items = []
    if write_dec.payload and "items" in write_dec.payload:
        items = write_dec.payload["items"]

    key = api_key_override
    inbox_ids = []
    for item in items:
        content = item.get("content", "")
        mem_type = item.get("type", "context_note")
        scope = item.get("scope", "unknown")
        tags_str = "memory-capture,autopilot,%s,%s" % (mem_type, scope)

        text = "[Autopilot] %s\nType: %s\nScope: %s\n---\n%s" % (
            mem_type.replace("_", " ").title(),
            mem_type,
            scope,
            content[:800],
        )

        # Write to inbox via API
        result = _inbox_append(text, confidence=0.7, tags=tags_str.split(","), api_key_override=key)
        if result and result.get("success"):
            inbox_ids.append(result.get("id"))

    return {
        "writes_created": len(inbox_ids),
        "inbox_ids": inbox_ids,
    }


def execute_counter_capture(policy_result, user_id, api_key_override=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute counter-capture decisions. Creates counter inbox items."""
    counter_dec = policy_result.counter_capture
    if not counter_dec.should_run:
        return {"counter_created": 0, "counter_ids": []}

    items = []
    if counter_dec.payload and "items" in counter_dec.payload:
        items = counter_dec.payload["items"]

    key = api_key_override
    counter_ids = []
    for item in items:
        counterexample = item.get("counterexample", "")
        scope = item.get("scope", "unknown")
        tags_str = "counterexample,autopilot,%s" % scope

        text = "[Autopilot Counterexample]\nScope: %s\n---\n%s" % (
            scope,
            counterexample[:800],
        )

        result = _inbox_append(text, confidence=0.8, tags=tags_str.split(","), api_key_override=key)
        if result and result.get("success"):
            counter_ids.append(result.get("id"))

    return {
        "counter_created": len(counter_ids),
        "counter_ids": counter_ids,
    }


def execute_update(policy_result, user_id, api_key_override=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute update decisions. Creates review items in inbox."""
    update_dec = policy_result.update
    if not update_dec.should_run:
        return {"updates_created": 0, "review_ids": []}

    key = api_key_override
    payload = update_dec.payload or {}
    operation = payload.get("operation", "review")
    scope = payload.get("scope", "unknown")

    text = "[Autopilot Update Review]\nOperation: %s\nScope: %s\nReason: %s" % (
        operation,
        scope,
        update_dec.reason,
    )

    result = _inbox_append(text, confidence=0.6, tags=["update-review", "autopilot", operation], api_key_override=key)
    review_id = result.get("id") if result and result.get("success") else None

    return {
        "updates_created": 1 if review_id else 0,
        "review_ids": [review_id] if review_id else [],
    }


# ── Internal helpers ──


def _inbox_append(text, confidence=0.7, tags=None, api_key_override=None):
    # type: (str, float, Optional[List[str]], Optional[str]) -> Optional[Dict[str, Any]]
    """Append an item to the Minta inbox via API."""
    if not text:
        return None
    qs = "?text=%s&confidence=%s" % (
        urllib.parse.quote(text[:1000]),
        confidence,
    )
    body = tags or []
    result = _api_post("/api/inbox/append%s" % qs, body, api_key_override=api_key_override)
    if result is None:
        # Try once more with env key as fallback
        fallback_key = os.environ.get("MINTA_API_KEY", "")
        if fallback_key and not api_key_override:
            result = _api_post("/api/inbox/append%s" % qs, body, api_key_override=fallback_key)
    return result


def execute_all(policy_result, user_id, api_key_override=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute all decisions from a policy result.
    This is the main entry point for the executor."""
    key = api_key_override
    result = {
        "user_id": user_id,
        "phase": policy_result.phase,
        "read": execute_read(policy_result, user_id, api_key_override=key),
        "write": execute_write(policy_result, user_id, api_key_override=key),
        "counter_capture": execute_counter_capture(policy_result, user_id, api_key_override=key),
        "update": execute_update(policy_result, user_id, api_key_override=key),
    }

    result["summary"] = {
        "read_performed": result["read"]["read_performed"],
        "writes_created": result["write"]["writes_created"],
        "counter_created": result["counter_capture"]["counter_created"],
        "updates_created": result["update"]["updates_created"],
        "total_created": (
            result["write"]["writes_created"]
            + result["counter_capture"]["counter_created"]
            + result["update"]["updates_created"]
        ),
    }

    return result
