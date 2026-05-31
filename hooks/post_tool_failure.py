#!/usr/bin/env python
"""PostToolUseFailure hook — auto-mark failed tool calls as counter-examples.

Reads JSON from stdin with error context.
"""
import json
import os
import sys
import urllib.request

API_KEY = os.environ.get("MINTA_API_KEY", "")
API_URL = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "")


def send_failure(obs: dict):
    if not API_KEY:
        return
    try:
        body = json.dumps(obs).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/sessions/{SESSION_ID}/observe",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        from buffer import write
        write({"session_id": SESSION_ID, **obs})


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return

    error_msg = data.get("error", "") or data.get("tool_output", "") or ""
    tool_name = data.get("tool_name", "unknown")

    send_failure({
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
