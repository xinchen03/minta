"""Env-gated credential gate tests (AMC auth contract)."""
from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from eval_app import create_eval_app  # noqa: E402

_SEARCH = {"query": "hello", "user_id": "u1", "top_k": 10}


def _client(tmp_path, env: dict | None = None) -> TestClient:
    old = os.environ.get("MINTA_EVAL_API_KEY")
    if env is None:
        os.environ.pop("MINTA_EVAL_API_KEY", None)
    else:
        os.environ.update(env)
    try:
        db_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
        app = create_eval_app(db_url=db_url)
    finally:
        if old is None:
            os.environ.pop("MINTA_EVAL_API_KEY", None)
        else:
            os.environ["MINTA_EVAL_API_KEY"] = old
    return TestClient(app)


def test_gate_off_by_default(tmp_path):
    c = _client(tmp_path)
    assert c.get("/health").json() == {"ok": True}
    assert c.post("/search", json=_SEARCH).status_code == 200


def test_gate_enforced_when_key_set(tmp_path):
    c = _client(tmp_path, {"MINTA_EVAL_API_KEY": "secret"})
    assert c.post("/search", json=_SEARCH).status_code == 401
    assert "invalid credential" in c.post("/search", json=_SEARCH).text
    assert c.post("/search", json=_SEARCH,
                  headers={"x-api-key": "wrong"}).status_code == 401
    assert c.post("/search", json=_SEARCH,
                  headers={"x-api-key": "secret"}).status_code == 200
    assert c.post("/search", json=_SEARCH,
                  headers={"Authorization": "Bearer secret"}).status_code == 200


def test_health_always_open(tmp_path):
    c = _client(tmp_path, {"MINTA_EVAL_API_KEY": "secret"})
    assert c.get("/health").json() == {"ok": True}
