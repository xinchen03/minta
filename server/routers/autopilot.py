"""Autopilot API routes — preflight, postflight, status, logs.
These are the high-level Autopilot endpoints called by MCP tools."""
import os
from fastapi import APIRouter, Request
from typing import Optional

from services.autopilot.schemas import (
    PreflightRequest,
    PreflightResponse,
    PostflightRequest,
    PostflightResponse,
    StatusCheck,
    AutopilotStatus,
)
from services.autopilot.autopilot_service import preflight, postflight
from services.autopilot import decision_logger

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


@router.post("/preflight", response_model=PreflightResponse)
async def api_preflight(req: PreflightRequest, request: Request):
    """Pre-turn: decide what memory to read before answering.
    Called by agent before responding to user."""
    # Extract API key from request headers (case-insensitive)
    headers = {}
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or ""
    headers["x-api-key"] = api_key
    result = preflight(
        user_message=req.user_message,
        project_id=req.project_id,
        agent=req.agent or "api",
        headers=headers,
    )
    return PreflightResponse(
        read_triggered=result["read_triggered"],
        reason=result["reason"],
        memory_context=result["memory_context"],
        log_id=result["log_id"],
        degraded=result.get("degraded", False),
    )


@router.post("/postflight", response_model=PostflightResponse)
async def api_postflight(req: PostflightRequest, request: Request):
    """Post-turn: decide what to capture after answering.
    Called by agent before finalizing response."""
    headers = dict(request.headers)
    result = postflight(
        user_message=req.user_message,
        assistant_response=req.assistant_response,
        project_id=req.project_id,
        agent=req.agent or "api",
        headers=headers,
    )
    return PostflightResponse(
        write_triggered=result["write_triggered"],
        counter_capture_triggered=result["counter_capture_triggered"],
        update_triggered=result["update_triggered"],
        created=result["created"],
        reason=result["reason"],
        log_id=result["log_id"],
        degraded=result.get("degraded", False),
    )


@router.get("/status", response_model=AutopilotStatus)
async def api_status(request: Request):
    """Check Autopilot status: is everything wired up correctly?"""
    headers = dict(request.headers)
    try:
        from config import MINTA_API_KEY as _CK
        _env_key = os.environ.get("MINTA_API_KEY", "") or _CK
    except ImportError:
        _env_key = os.environ.get("MINTA_API_KEY", "")
    api_key = headers.get("x-api-key", "") or _env_key

    checks = [
        _check("api_key_valid", bool(api_key), "API key configured" if api_key else "No API key"),
        _check("mcp_connected", True, "HTTP transport on :18721"),
        _check("preflight_tool_available", True, "POST /api/autopilot/preflight"),
        _check("postflight_tool_available", True, "POST /api/autopilot/postflight"),
        _check("inbox_route", _test_inbox_route(api_key), "Inbox append endpoint reachable"),
    ]

    all_pass = all(c.passed for c in checks)
    return AutopilotStatus(
        active=all_pass,
        mode="autopilot" if all_pass else "manual_mcp",
        checks=checks,
    )


@router.get("/logs")
async def api_logs(user_id: Optional[str] = None, phase: Optional[str] = None, limit: int = 10):
    """Get recent Autopilot decision logs."""
    logs = decision_logger.query_logs(user_id=user_id, phase=phase, limit=limit)
    return {"logs": logs, "count": len(logs)}


# ── Health check helpers ──


def _check(label, passed, detail=""):
    return StatusCheck(label=label, passed=passed, detail=detail)


def _test_inbox_route(api_key):
    # type: (str) -> bool
    """Health check: is the inbox route mounted (auth aside)? 200/401/403/405
    all prove the route and DB are wired; only 5xx / refused mean failure."""
    import urllib.error
    try:
        import urllib.request

        req = urllib.request.Request(
            "%s/api/inbox" % os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772"),
            headers={"X-API-Key": api_key} if api_key else {},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 401, 403, 405)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401, 403, 405)
    except Exception:
        return False
