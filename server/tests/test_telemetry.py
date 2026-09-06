"""Telemetry module tests: opt-in gating + metadata-only payload."""
from __future__ import annotations

import os
import sys

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from services import telemetry  # noqa: E402

ALLOWED_KEYS = {"api_key", "distinct_id", "event", "properties",
                "app", "version", "os", "source", "id"}


def _fake_post(out: list):
    def fake_post(url, json=None, timeout=None):
        out.append(json)

        class R:
            status_code = 200
            text = "ok"
        return R()
    return fake_post


def test_disabled_sends_nothing(monkeypatch):
    import requests as real_requests
    out: list = []
    monkeypatch.setattr(real_requests, "post", _fake_post(out))
    monkeypatch.setenv("MINTA_TELEMETRY", "0")
    monkeypatch.setenv("MINTA_TELEMETRY_POSTHOG_KEY", "phc_test")
    telemetry.heartbeat()
    assert out == []  # default off — even with a key set


def test_payload_is_metadata_only(monkeypatch):
    import requests as real_requests
    out: list = []
    monkeypatch.setattr(real_requests, "post", _fake_post(out))
    monkeypatch.setenv("MINTA_TELEMETRY", "1")
    monkeypatch.setenv("MINTA_TELEMETRY_POSTHOG_KEY", "phc_test")
    monkeypatch.setenv("MINTA_TELEMETRY_INSTALL_ID", "install-123")
    telemetry.heartbeat({"source": "test"})
    assert len(out) == 1
    p = out[0]
    assert p["event"] == "heartbeat"
    assert p["distinct_id"] == "install-123"
    assert p["api_key"] == "phc_test"
    assert set(p["properties"].keys()) <= ALLOWED_KEYS
    assert "content" not in p  # no memory content, ever


def test_file_consent_enables_sends(monkeypatch, tmp_path):
    import requests as real_requests
    out: list = []
    monkeypatch.setattr(real_requests, "post", _fake_post(out))
    monkeypatch.setenv("MINTA_TELEMETRY", "0")  # env says off
    monkeypatch.setenv("MINTA_TELEMETRY_POSTHOG_KEY", "phc_test")
    monkeypatch.setenv("MINTA_TELEMETRY_INSTALL_ID", "x")
    f = tmp_path / ".telemetry_consent"
    f.write_text("1", encoding="utf-8")
    monkeypatch.setattr(telemetry, "_CONSENT_FILE", f)
    telemetry.heartbeat()
    assert len(out) == 1  # file consent overrides env


def test_file_optout_wins_no_send(monkeypatch, tmp_path):
    import requests as real_requests
    out: list = []
    monkeypatch.setattr(real_requests, "post", _fake_post(out))
    monkeypatch.setenv("MINTA_TELEMETRY", "1")  # env says on
    monkeypatch.setenv("MINTA_TELEMETRY_POSTHOG_KEY", "phc_test")
    f = tmp_path / ".telemetry_consent"
    f.write_text("0", encoding="utf-8")
    monkeypatch.setattr(telemetry, "_CONSENT_FILE", f)
    telemetry.heartbeat()
    assert out == []  # user opt-out wins


def test_missing_key_sends_nothing(monkeypatch):
    import requests as real_requests
    out: list = []
    monkeypatch.setattr(real_requests, "post", _fake_post(out))
    monkeypatch.setenv("MINTA_TELEMETRY", "1")
    monkeypatch.delenv("MINTA_TELEMETRY_POSTHOG_KEY", raising=False)
    telemetry.heartbeat()
    assert out == []
