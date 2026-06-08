#!/usr/bin/env python
"""PostToolUse hook — detect correction signals in tool output.

Reads JSON from stdin (Claude Code hook protocol):
  {
    "session_id": "...",
    "tool_name": "Bash|Write|Edit|...",
    "tool_input": {...},
    "tool_response": "string output" | {"stdout": "...", "stderr": "...", "exitCode": 0},
    "cwd": "...",
    "hook_event_name": "PostToolUse"
  }

If correction/preference/pending signals detected, sends to Minta API.
If API unreachable, buffers locally.
"""
import json
import os
import re
import sys
import urllib.request

API_KEY = os.environ.get("MINTA_API_KEY", "")
API_URL = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")

# Quick signal patterns (same as reflect.py, simplified for hook)
PATTERNS = [
    (r"(?:不对|不是这样|错了|不要|别|停止|不能这样|不应该|不许)", "correction"),
    (r"(?:应该|最好|推荐|建议|倾向于|下次|以后|记得|别忘了|习惯|喜欢)", "preference"),
    (r"(?:还没|还没做|todo|TODO|待办|未完成|接下来|还需要)", "pending"),
]


def _extract_text(tool_response) -> str:
    """Handle both string and object tool_response formats."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        # Bash-style: {"stdout": "...", "stderr": "...", "exitCode": 0}
        parts = []
        stdout = tool_response.get("stdout", "")
        stderr = tool_response.get("stderr", "")
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(stderr)
        return "\n".join(parts)
    return ""


def detect_signals(text: str) -> list:
    if not text or len(text) < 10:
        return []
    signals = []
    for pattern, sig_type in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 70)
            signals.append({
                "type": sig_type,
                "content": text[start:end].strip()[:250],
            })
    # Deduplicate
    seen = set()
    unique = []
    for s in signals:
        key = (s["type"], s["content"][:60])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique[:5]


def send_observation(obs: dict) -> bool:
    if not API_KEY:
        return False
    session_id = obs.get("session_id", "")
    if not session_id:
        return False
    try:
        body = json.dumps(obs).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/sessions/{session_id}/observe",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


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

    # ── Extract text from tool_response (NOT tool_output — that field doesn't exist) ──
    tool_response = data.get("tool_response", "") or ""
    text = _extract_text(tool_response)

    if len(text) < 20:
        return

    signals = detect_signals(text)
    if not signals:
        return

    api_ok = False
    for sig in signals:
        obs = {
            "session_id": session_id,
            "type": sig["type"],
            "content": sig["content"],
            "tool_name": data.get("tool_name", ""),
            "tool_output": text[:500],  # keep "tool_output" key for server-side compatibility
        }
        if send_observation(obs):
            api_ok = True
        else:
            # Buffer for later
            from buffer import write
            write({"session_id": session_id, **obs})

    if api_ok:
        sys.stderr.write(f"[Minta] Detected {len(signals)} signal(s)\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # non-blocking
    sys.stderr.write("[Minta] hook ok (non-blocking)\n")
    sys.exit(0)
