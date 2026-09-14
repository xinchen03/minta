from services.autopilot.schemas import PolicyResult, Decision
from services.autopilot import memory_executor as executor


def test_execute_read_uses_policy_queries(monkeypatch):
    calls = []

    def fake_post(path, body, api_key_override=None, auth_headers=None):
        calls.append((path, body))
        if path == "/api/search":
            return {"results": [{
                "id": 7,
                "title": "Python preference",
                "summary": "Use Python",
                "body": "Prefer Python for this project",
                "score": 0.91,
                "type": body.get("type"),
            }]}
        return None

    def fake_get(path, api_key_override=None, auth_headers=None):
        if path == "/api/skills":
            return []
        if path == "/api/inbox":
            return {"archived": []}
        return None

    monkeypatch.setattr(executor, "_api_post", fake_post)
    monkeypatch.setattr(executor, "_api_get", fake_get)

    policy = PolicyResult(
        phase="pre_turn",
        read=Decision(True, 0.9, "test", {"queries": [{
            "type": "user_preferences",
            "query": "python project preference",
        }]}),
    )

    result = executor.execute_read(policy, "u1")
    assert result["memory_context"]["user_preferences"][0]["title"] == "Python preference"
    assert calls[0][0] == "/api/search"
    assert calls[0][1]["query"] == "python project preference"
    assert calls[0][1]["type"] == "preference"
