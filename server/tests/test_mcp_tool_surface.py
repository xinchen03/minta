"""Community MCP advertises only routes that ship in the public engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import minta_mcp
from minta_mcp import TOOL_DEFINITIONS
from minta_mcp_http import create_mcp_app
from fastapi.testclient import TestClient


def test_community_mcp_has_13_working_tools():
    names = {tool["name"] for tool in TOOL_DEFINITIONS}
    assert len(names) == 13
    assert "minta_read_context" in names
    assert "minta_autopilot_preflight" in names
    assert "minta_autopilot_postflight" in names
    assert not any(name.startswith("minta_expert_") for name in names)
    assert "minta_chat" not in names


def test_mcp_http_rejects_untrusted_browser_origin():
    with TestClient(create_mcp_app()) as client:
        r = client.options("/mcp", headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        })
    assert "access-control-allow-origin" not in r.headers


def test_mcp_login_does_not_claim_unregistered_api_key_is_valid(monkeypatch):
    monkeypatch.setattr(minta_mcp, "API_KEY", "minta_unregistered")
    monkeypatch.setattr(minta_mcp, "api_key_ready", False)
    monkeypatch.setattr(
        minta_mcp, "_api",
        lambda *args, **kwargs: {"error": "HTTP 401: invalid key"},
    )
    assert "登录失败" in minta_mcp.minta_login("", "")


def test_mcp_uses_explicit_config_key_when_environment_is_not_preloaded(monkeypatch):
    """The stdio/HTTP launcher must see an operator key loaded from .env."""
    import config

    monkeypatch.delenv("MINTA_API_KEY", raising=False)
    assert minta_mcp._configured_api_key("") == config.MINTA_API_KEY


def test_autopilot_preflight_delegates_to_authenticated_api(monkeypatch):
    seen = {}

    def fake_api(method, path, token="", body=None):
        seen.update(method=method, path=path, body=body)
        return {
            "read_triggered": True,
            "memory_context": {"user_preferences": [{"title": "真实偏好"}]},
            "degraded": False,
        }

    monkeypatch.setattr(minta_mcp, "_api", fake_api)
    result = minta_mcp.handle_call(
        "minta_autopilot_preflight",
        {"user_message": "继续上次的工作", "project_id": "e2e"},
    )

    assert seen == {
        "method": "POST",
        "path": "/api/autopilot/preflight",
        "body": {
            "user_message": "继续上次的工作",
            "project_id": "e2e",
            "agent": "mcp",
        },
    }
    assert "真实偏好" in result
