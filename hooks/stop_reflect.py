#!/usr/bin/env python
"""Stop hook — trigger slot reflection at session end.

Called when Claude Code session ends.
Reads CLAUDE_SESSION_ID from environment (primary — always safe, never blocks).
"""
import json
import os
import sys
import urllib.request

API_KEY = os.environ.get("MINTA_API_KEY", "")
API_URL = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "")


def trigger_reflect():
    if not API_KEY or not SESSION_ID:
        return

    try:
        # Start session if not exists
        body = json.dumps({"session_id": SESSION_ID}).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/sessions/start",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    try:
        # Trigger reflection with empty observations
        # (the server-side reflect scans recent observations if available)
        body = json.dumps({"observations": []}).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/sessions/{SESSION_ID}/reflect",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                sys.stderr.write(f"[Minta] Reflection completed for {SESSION_ID}\n")
    except Exception as e:
        sys.stderr.write(f"[Minta] Reflection skipped: {e}\n")


if __name__ == "__main__":
    try:
        trigger_reflect()
    except Exception:
        pass  # stop hook: never block shutdown
    sys.stderr.write("[Minta] stop hook ok\n")
    sys.exit(0)
