"""Security regression tests for the public Autopilot HTTP surface."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app
from routers import autopilot as autopilot_router
from routers.auth import get_current_user
from services.autopilot import memory_executor


class _User:
    id = 42


def _authorized_client():
    app.dependency_overrides[get_current_user] = lambda: _User()
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_autopilot_routes_reject_unauthenticated_requests():
    client = TestClient(app)
    assert client.post("/api/autopilot/preflight", json={"user_message": "hello"}).status_code == 401
    assert client.post(
        "/api/autopilot/postflight",
        json={"user_message": "hello", "assistant_response": "hi"},
    ).status_code == 401
    assert client.get("/api/autopilot/status").status_code == 401
    assert client.get("/api/autopilot/logs").status_code == 401


def test_preflight_uses_authenticated_user_and_forwards_bearer(monkeypatch):
    seen = {}

    def fake_preflight(**kwargs):
        seen.update(kwargs)
        return {
            "read_triggered": False,
            "reason": "test",
            "memory_context": {},
            "log_id": "log-1",
            "degraded": False,
        }

    monkeypatch.setattr(autopilot_router, "preflight", fake_preflight)
    response = _authorized_client().post(
        "/api/autopilot/preflight",
        headers={"Authorization": "Bearer caller-token"},
        json={"user_message": "hello"},
    )

    assert response.status_code == 200
    assert seen["user_id"] == "42"
    assert seen["headers"] == {"Authorization": "Bearer caller-token"}


def test_logs_are_forced_to_authenticated_user(monkeypatch):
    seen = {}

    def fake_query_logs(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(autopilot_router.decision_logger, "query_logs", fake_query_logs)
    response = _authorized_client().get("/api/autopilot/logs?limit=5")

    assert response.status_code == 200
    assert seen == {"user_id": "42", "phase": None, "limit": 5}


def test_executor_never_falls_back_to_server_api_key(monkeypatch):
    monkeypatch.setenv("MINTA_API_KEY", "minta_server_secret")
    assert "X-API-Key" not in memory_executor._headers()
    assert memory_executor._headers(auth_headers={"X-API-Key": "minta_caller"})["X-API-Key"] == "minta_caller"


def test_preflight_offloads_blocking_executor_from_event_loop(monkeypatch):
    calls = []

    def fake_preflight(**kwargs):
        return {
            "read_triggered": False,
            "reason": "direct-call-must-not-run",
            "memory_context": {},
            "log_id": "log-direct",
            "degraded": False,
        }

    async def fake_run_in_threadpool(func, **kwargs):
        calls.append((func, kwargs))
        return {
            "read_triggered": False,
            "reason": "test",
            "memory_context": {},
            "log_id": "log-threaded",
            "degraded": False,
        }

    monkeypatch.setattr(autopilot_router, "preflight", fake_preflight)
    monkeypatch.setattr(autopilot_router, "run_in_threadpool", fake_run_in_threadpool, raising=False)
    response = _authorized_client().post(
        "/api/autopilot/preflight",
        headers={"Authorization": "Bearer caller-token"},
        json={"user_message": "hello"},
    )

    assert response.status_code == 200
    assert calls and calls[0][0] is fake_preflight
