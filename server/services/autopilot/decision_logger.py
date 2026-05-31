"""Decision Logger — records every Autopilot decision for auditability.
Each preflight/postflight call produces one log entry.
Logs can be queried by user_id, project_id, agent, phase, time range."""
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.autopilot.schemas import AutopilotLogStatus

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
    "autopilot",
)


def _ensure_log_dir():
    # type: () -> str
    """Create log directory if it doesn't exist."""
    d = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m"))
    if not os.path.exists(d):
        try:
            os.makedirs(d)
        except OSError:
            pass
    return d


def _next_id():
    # type: () -> str
    """Generate a unique log ID."""
    return "apl_%s_%d" % (datetime.now().strftime("%Y%m%d%H%M%S"), int(time.time() * 1000) % 10000)


def write_log(entry):
    # type: (Dict[str, Any]) -> str
    """Write a decision log entry to both file and in-memory store.
    Returns the log_id."""
    log_id = entry.get("log_id") or _next_id()
    entry["log_id"] = log_id
    entry["timestamp"] = datetime.now().isoformat()

    # Write to file
    try:
        log_dir = _ensure_log_dir()
        log_file = os.path.join(log_dir, "%s.jsonl" % datetime.now().strftime("%Y-%m-%d"))
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except IOError:
        pass  # Logging must never break Autopilot

    # Also write to API if available
    _try_write_to_api(entry)

    return log_id


def _try_write_to_api(entry):
    # type: (Dict[str, Any]) -> None
    """Try to persist decision log to Minta API."""
    try:
        from config import MINTA_API_KEY as _CK
        api_key = os.environ.get("MINTA_API_KEY", "") or _CK
    except ImportError:
        api_key = os.environ.get("MINTA_API_KEY", "")
    api_url = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
    if not api_key:
        return

    try:
        import urllib.request

        data = json.dumps({
            "title": "Autopilot Decision: %s" % entry.get("phase", "unknown"),
            "type": "decision_criteria",
            "summary": entry.get("reason", "")[:200],
            "body": json.dumps(entry, ensure_ascii=False)[:2000],
            "tags": ["autopilot", "decision-log", entry.get("phase", "")],
            "source": "autopilot",
            "confidence": 3,
        }).encode("utf-8")
        req = urllib.request.Request(
            "%s/api/contextObjects" % api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key,
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def query_logs(user_id=None, phase=None, limit=10):
    # type: (Optional[str], Optional[str], int) -> List[Dict[str, Any]]
    """Query decision logs from files."""
    logs = []
    log_dir = _ensure_log_dir()

    try:
        files = sorted(os.listdir(log_dir), reverse=True)[:3]
        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(log_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line.strip())
                        if user_id and entry.get("user_id") != user_id:
                            continue
                        if phase and entry.get("phase") != phase:
                            continue
                        logs.append(entry)
            except (IOError, json.JSONDecodeError):
                continue
    except OSError:
        pass

    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs[:limit]
