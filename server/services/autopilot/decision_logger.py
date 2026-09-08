"""Decision Logger — records every Autopilot decision for auditability.
Each preflight/postflight call produces one log entry.
Logs can be queried by user_id, project_id, agent, phase, time range."""
import json
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.autopilot.schemas import AutopilotLogStatus

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
    "autopilot",
)
_LOG_LOCK = threading.RLock()


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
        with _LOG_LOCK:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except IOError:
        pass  # Logging must never break Autopilot

    return log_id


def _log_files():
    """Return every JSONL log file across all month directories."""
    if not os.path.isdir(LOG_DIR):
        return []
    files = []
    for entry in sorted(os.listdir(LOG_DIR), reverse=True):
        path = os.path.join(LOG_DIR, entry)
        if os.path.isfile(path) and entry.endswith(".jsonl"):
            files.append(path)
        elif os.path.isdir(path):
            files.extend(
                os.path.join(path, name)
                for name in sorted(os.listdir(path), reverse=True)
                if name.endswith(".jsonl")
            )
    return files


def query_logs(user_id=None, phase=None, limit=10, strict=False):
    # type: (Optional[str], Optional[str], Optional[int], bool) -> List[Dict[str, Any]]
    """Query decision logs; strict mode surfaces unreadable/malformed files."""
    logs = []
    try:
        with _LOG_LOCK:
            files = _log_files()
            for fpath in files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            entry = json.loads(line.strip())
                            if user_id and str(entry.get("user_id")) != str(user_id):
                                continue
                            if phase and entry.get("phase") != phase:
                                continue
                            logs.append(entry)
                except (IOError, json.JSONDecodeError):
                    if strict:
                        raise
                    continue
    except OSError:
        if strict:
            raise

    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return logs if limit is None else logs[:limit]


def delete_user_logs(user_id):
    # type: (str) -> int
    """Atomically purge every on-disk log entry owned by user_id.

    Any unreadable or malformed file is surfaced to the caller so a privacy
    request can never be reported as successful when its logs were untouched.
    """
    removed = 0
    if not os.path.isdir(LOG_DIR):
        return removed
    with _LOG_LOCK:
        for fpath in _log_files():
            kept = []
            removed_from_file = 0
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line.strip())
                        if str(entry.get("user_id")) == str(user_id):
                            removed_from_file += 1
                            continue
                        kept.append(line)
                fd, tmp = tempfile.mkstemp(
                    prefix=os.path.basename(fpath) + ".", suffix=".clean",
                    dir=os.path.dirname(fpath), text=True)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(kept)
                os.replace(tmp, fpath)
                removed += removed_from_file
            except Exception:
                if "tmp" in locals() and os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                raise
    return removed
