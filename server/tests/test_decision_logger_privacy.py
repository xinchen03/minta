"""Privacy behavior for Autopilot JSONL decision logs."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.autopilot import decision_logger


def _write(path: Path, entries: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def test_query_logs_reads_all_months_when_limit_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_logger, "LOG_DIR", str(tmp_path))
    _write(tmp_path / "2025-01" / "2025-01-01.jsonl", [
        {"user_id": "7", "timestamp": "2025-01-01T00:00:00"},
    ])
    _write(tmp_path / "2026-09" / "2026-09-08.jsonl", [
        {"user_id": "7", "timestamp": "2026-09-08T00:00:00"},
    ])
    rows = decision_logger.query_logs(user_id="7", limit=None)
    assert len(rows) == 2


def test_delete_user_logs_raises_when_atomic_replace_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_logger, "LOG_DIR", str(tmp_path))
    _write(tmp_path / "2026-09" / "2026-09-08.jsonl", [
        {"user_id": "7", "timestamp": "2026-09-08T00:00:00"},
    ])

    def fail_replace(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        decision_logger.delete_user_logs("7")
