"""Local buffer — used when hook can't reach the Minta API.
Stores observations as JSONL for later batch upload.
"""
import json
import os
from pathlib import Path

BUFFER_DIR = Path.home() / ".minta"
BUFFER_FILE = BUFFER_DIR / "observation_buffer.jsonl"
MAX_BUFFER = 100


def write(entry: dict):
    """Append an entry to the buffer."""
    BUFFER_DIR.mkdir(exist_ok=True)
    try:
        with open(BUFFER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # totally silent; don't block the hook


def flush(api_key: str, base_url: str = "http://127.0.0.1:8772") -> int:
    """Try to upload buffered entries. Returns count uploaded."""
    if not BUFFER_FILE.exists():
        return 0

    entries = []
    try:
        with open(BUFFER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception:
        return 0

    if not entries:
        BUFFER_FILE.unlink(missing_ok=True)
        return 0

    # Upload to API
    import urllib.request

    uploaded = 0
    for entry in entries[:MAX_BUFFER]:
        try:
            body = json.dumps(entry).encode()
            req = urllib.request.Request(
                f"{base_url}/api/sessions/{entry.get('session_id', 'unknown')}/observe",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    uploaded += 1
        except Exception:
            break

    # Remove uploaded entries
    remaining = entries[uploaded:]
    try:
        with open(BUFFER_FILE, "w", encoding="utf-8") as f:
            for e in remaining:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return uploaded
