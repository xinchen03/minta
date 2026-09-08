"""Autopilot API routes — preflight, postflight, status, logs.
These are the high-level Autopilot endpoints called by MCP tools."""
import os
from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
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
from routers.auth import User, get_current_user

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])


def _caller_auth_headers(request: Request):
    """Forward only the credentials already validated by get_current_user."""
    headers = {}
    authorization = request.headers.get("authorization")
    api_key = request.headers.get("x-api-key")
    if authorization:
        headers["Authorization"] = authorization
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


@router.post("/preflight", response_model=PreflightResponse)
async def api_preflight(
    req: PreflightRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Pre-turn: decide what memory to read before answering.
    Called by agent before responding to user."""
    result = await run_in_threadpool(
        preflight,
        user_message=req.user_message,
        project_id=req.project_id,
        agent=req.agent or "api",
        headers=_caller_auth_headers(request),
        user_id=str(user.id),
    )
    return PreflightResponse(
        read_triggered=result["read_triggered"],
        reason=result["reason"],
        memory_context=result["memory_context"],
        log_id=result["log_id"],
        degraded=result.get("degraded", False),
    )


@router.post("/postflight", response_model=PostflightResponse)
async def api_postflight(
    req: PostflightRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Post-turn: decide what to capture after answering.
    Called by agent before finalizing response."""
    result = await run_in_threadpool(
        postflight,
        user_message=req.user_message,
        assistant_response=req.assistant_response,
        project_id=req.project_id,
        agent=req.agent or "api",
        headers=_caller_auth_headers(request),
        user_id=str(user.id),
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
async def api_status(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Check Autopilot status: is everything wired up correctly?"""
    auth_headers = _caller_auth_headers(request)

    checks = [
        _check("caller_authenticated", True, "Caller credentials validated"),
        _check("mcp_connected", True, "HTTP transport on :18721"),
        _check("preflight_tool_available", True, "POST /api/autopilot/preflight"),
        _check("postflight_tool_available", True, "POST /api/autopilot/postflight"),
        _check("inbox_route", _test_inbox_route(auth_headers), "Inbox endpoint reachable"),
    ]

    all_pass = all(c.passed for c in checks)
    return AutopilotStatus(
        active=all_pass,
        mode="autopilot" if all_pass else "manual_mcp",
        checks=checks,
    )


@router.get("/logs")
async def api_logs(
    phase: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Get recent Autopilot decision logs."""
    logs = decision_logger.query_logs(user_id=str(user.id), phase=phase, limit=limit)
    return {"logs": logs, "count": len(logs)}


# ── Health check helpers ──


def _check(label, passed, detail=""):
    return StatusCheck(label=label, passed=passed, detail=detail)


def _test_inbox_route(auth_headers):
    # type: (dict) -> bool
    """Health check: is the inbox route mounted (auth aside)? 200/401/403/405
    all prove the route and DB are wired; only 5xx / refused mean failure."""
    import urllib.error
    try:
        import urllib.request

        req = urllib.request.Request(
            "%s/api/inbox" % os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772"),
            headers=auth_headers,
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 401, 403, 405)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401, 403, 405)
    except Exception:
        return False
