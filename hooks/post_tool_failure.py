#!/usr/bin/env python
"""PostToolUseFailure hook — auto-mark failed tool calls as counter-examples.

Reads JSON from stdin (Claude Code hook protocol):
  {
    "session_id": "...",
    "tool_name": "...",
    "tool_input": {...},
    "tool_response": "error string" | {"stdout": "...", "stderr": "...", "exitCode": 1},
    "cwd": "...",
    "hook_event_name": "PostToolUseFailure"
  }
"""
import json
import os
import sys
import urllib.request

API_KEY = os.environ.get("MINTA_API_KEY", "")
API_URL = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")


def _extract_error(tool_response) -> str:
    """Handle both string and object tool_response formats."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        stderr = tool_response.get("stderr", "")
        stdout = tool_response.get("stdout", "")
        return stderr or stdout or ""
    return ""


def send_failure(obs: dict):
    if not API_KEY:
        return
    session_id = obs.get("session_id", "")
    if not session_id:
        return
    try:
        body = json.dumps(obs).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/sessions/{session_id}/observe",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        from buffer import write
        write({"session_id": session_id, **obs})


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return

    # ── Get session_id from stdin JSON (primary) or env var (fallback) ──
    session_id = data.get("session_id", "") or os.environ.get("CLAUDE_SESSION_ID", "")

    # ── Extract error from tool_response ──
    tool_response = data.get("tool_response", "") or ""
    error_msg = _extract_error(tool_response)
    tool_name = data.get("tool_name", "unknown")

    if not error_msg:
        error_msg = f"Tool {tool_name} failed"

    send_failure({
        "session_id": session_id,
        "type": "correction",
        "content": f"[FAILURE] {tool_name}: {error_msg[:300]}",
        "tool_name": tool_name,
        "tool_output": error_msg[:300],
    })

    sys.stderr.write(f"[Minta] Failure logged: {tool_name}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.stderr.write("[Minta] failure hook ok (non-blocking)\n")
    sys.exit(0)
