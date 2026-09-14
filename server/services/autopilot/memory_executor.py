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

import logging

_AUTOPILOT_LOG = logging.getLogger("minta.autopilot")


def _api_key(override=None):
    # type: (Optional[str]) -> str
    """Return only the caller-provided API key; never borrow a server key."""
    key = override or ""
    if not key:
        _AUTOPILOT_LOG.warning("No API key available for autopilot executor")
    return key


# ── HTTP helpers ──


def _headers(key_override=None, auth_headers=None):
    """Build headers from the authenticated caller's credentials only."""
    h = {"Content-Type": "application/json"}
    for name, value in (auth_headers or {}).items():
        lower = name.lower()
        if lower == "authorization" and value:
            h["Authorization"] = value
        elif lower == "x-api-key" and value:
            h["X-API-Key"] = value
    k = _api_key(key_override)
    if k and "X-API-Key" not in h:
        h["X-API-Key"] = k
    return h


def _api_get(path, api_key_override=None, auth_headers=None):
    # type: (str, Optional[str]) -> Optional[Dict[str, Any]]
    """GET request to Minta API."""
    try:
        req = urllib.request.Request(
            "%s%s" % (MINTA_API, path),
            headers=_headers(api_key_override, auth_headers),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _api_post(path, body, api_key_override=None, auth_headers=None):
    # type: (str, dict, Optional[str]) -> Optional[Dict[str, Any]]
    """POST request to Minta API."""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            "%s%s" % (MINTA_API, path),
            data=data,
            headers=_headers(api_key_override, auth_headers),
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


def _context_result(entry):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """Normalize one search result into the compact autopilot context shape."""
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "summary": entry.get("summary", ""),
        "body": entry.get("body", ""),
        "score": entry.get("score"),
        "type": entry.get("type"),
    }


def _search_context(query, obj_type=None, top_k=8, api_key_override=None, auth_headers=None):
    # type: (str, Optional[str], int, Optional[str], Optional[Dict[str, str]]) -> List[Dict[str, Any]]
    """Run the query the policy actually produced against Minta search."""
    body = {
        "query": query,
        "top_k": top_k,
        "layer": "pack",
    }
    if obj_type:
        body["type"] = obj_type
    response = _api_post(
        "/api/search", body,
        api_key_override=api_key_override,
        auth_headers=auth_headers,
    )
    if not response or not isinstance(response, dict):
        return []
    return [
        _context_result(item)
        for item in response.get("results", [])
        if isinstance(item, dict)
    ]


def execute_read(policy_result, user_id, api_key_override=None, auth_headers=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute the policy's retrieval plan, not a generic memory shelf read.

    The policy decides *what to ask*. This layer now preserves that intent and
    sends each query through the existing semantic search API. The returned
    shape stays backwards-compatible for callers that already consume
    ``memory_context``.
    """
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
    seen = {name: set() for name in memory_context}

    for spec in queries:
        if not isinstance(spec, dict):
            continue
        bucket = spec.get("type")
        query = (spec.get("query") or "").strip()
        if not query or bucket not in memory_context:
            continue

        # Policy buckets are semantic concepts; context-object types are storage
        # labels. Keep this mapping small and explicit.
        storage_types = {
            "user_preferences": ["preference"],
            "project_context": ["project_context", "decision_criteria"],
            "counterexamples": ["counterexample"],
        }.get(bucket, [])

        for storage_type in storage_types:
            for item in _search_context(
                query,
                obj_type=storage_type,
                top_k=8,
                api_key_override=key,
                auth_headers=auth_headers,
            ):
                item_id = item.get("id")
                dedupe_key = item_id if item_id is not None else (item.get("title"), item.get("summary"))
                if dedupe_key in seen[bucket]:
                    continue
                seen[bucket].add(dedupe_key)
                memory_context[bucket].append(item)
                if len(memory_context[bucket]) >= 10:
                    break
            if len(memory_context[bucket]) >= 10:
                break

    # Legacy counterexamples may still live only in archived inbox entries.
    # Use them as a fallback, not as the primary retrieval path.
    if not memory_context["counterexamples"]:
        inbox = _api_get("/api/inbox", key, auth_headers)
        if inbox and isinstance(inbox, dict):
            archived = inbox.get("archived", [])
            memory_context["counterexamples"] = [
                {"title": item.get("title", ""), "body": item.get("body", "")}
                for item in archived[:10]
            ]

    skills = _api_get("/api/skills", key, auth_headers)
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


def execute_write(policy_result, user_id, api_key_override=None, auth_headers=None):
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
        result = _inbox_append(
            text, confidence=0.7, tags=tags_str.split(","),
            api_key_override=key, auth_headers=auth_headers,
        )
        if result and result.get("success"):
            inbox_ids.append(result.get("id"))

    return {
        "writes_created": len(inbox_ids),
        "inbox_ids": inbox_ids,
    }


def execute_counter_capture(policy_result, user_id, api_key_override=None, auth_headers=None):
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

        result = _inbox_append(
            text, confidence=0.8, tags=tags_str.split(","),
            api_key_override=key, auth_headers=auth_headers,
        )
        if result and result.get("success"):
            counter_ids.append(result.get("id"))

    return {
        "counter_created": len(counter_ids),
        "counter_ids": counter_ids,
    }


def execute_update(policy_result, user_id, api_key_override=None, auth_headers=None):
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

    result = _inbox_append(
        text, confidence=0.6, tags=["update-review", "autopilot", operation],
        api_key_override=key, auth_headers=auth_headers,
    )
    review_id = result.get("id") if result and result.get("success") else None

    return {
        "updates_created": 1 if review_id else 0,
        "review_ids": [review_id] if review_id else [],
    }


# ── Internal helpers ──


def _inbox_append(text, confidence=0.7, tags=None, api_key_override=None, auth_headers=None):
    # type: (str, float, Optional[List[str]], Optional[str]) -> Optional[Dict[str, Any]]
    """Append an item to the Minta inbox via API."""
    if not text:
        return None
    qs = "?text=%s&confidence=%s" % (
        urllib.parse.quote(text[:1000]),
        confidence,
    )
    body = tags or []
    return _api_post(
        "/api/inbox/append%s" % qs,
        body,
        api_key_override=api_key_override,
        auth_headers=auth_headers,
    )


def execute_all(policy_result, user_id, api_key_override=None, auth_headers=None):
    # type: (PolicyResult, str, Optional[str]) -> Dict[str, Any]
    """Execute all decisions from a policy result.
    This is the main entry point for the executor."""
    key = api_key_override
    result = {
        "user_id": user_id,
        "phase": policy_result.phase,
        "read": execute_read(policy_result, user_id, api_key_override=key, auth_headers=auth_headers),
        "write": execute_write(policy_result, user_id, api_key_override=key, auth_headers=auth_headers),
        "counter_capture": execute_counter_capture(policy_result, user_id, api_key_override=key, auth_headers=auth_headers),
        "update": execute_update(policy_result, user_id, api_key_override=key, auth_headers=auth_headers),
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
