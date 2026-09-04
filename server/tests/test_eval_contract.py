"""Contract tests for the AMC eval adapter (D1–D5 slices).

Covers the Agent Memory Leaderboard Add/Search contract:
atomic multi-message ingest, request_id idempotency, deterministic ids,
strict user isolation, envelope/created_at provenance, neighbour-window
bounds, dedupe suppression and top_k fill.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from eval_store import EvalStore, mem_id, AddRequest, Memory  # noqa: E402
from eval_app import create_eval_app  # noqa: E402
from eval_experiments import set_embed_fn  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def make_bow_embedder(dim: int = 256):
    """Deterministic bag-of-words embedder for unit tests (no model needed)."""
    vocab: dict[str, int] = {}

    def embed(text: str) -> np.ndarray:
        v = np.zeros(dim, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9']+", text.lower()):
            if tok not in vocab:
                vocab[tok] = len(vocab) % dim
            v[vocab[tok]] += 1.0
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    return embed


def add_payload(request_id: str, user_id: str, session_id: str,
                texts: list[tuple[str, str]], ts_start: int = 1_700_000_000_000):
    msgs = []
    for i, (role, content) in enumerate(texts):
        m = {"role": role, "content": content}
        if ts_start is not None:
            m["timestamp"] = ts_start + i * 60_000
        msgs.append(m)
    return {
        "request_id": request_id,
        "user_id": user_id,
        "session_id": session_id,
        "messages": msgs,
    }


@pytest.fixture()
def client(tmp_path):
    """Eval app on a temp DB with the deterministic embedder attached."""
    db_url = f"sqlite:///{(tmp_path / 'eval_test.db').as_posix()}"
    bow = make_bow_embedder()
    set_embed_fn(bow)
    app = create_eval_app(db_url=db_url, embed_fn=bow)
    with TestClient(app) as c:
        yield c


# ── Add contract ───────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_add_echo_byte_identical(client):
    body = add_payload("req-1", "eval:run:locomo:conv-0", "sess/01",
                       [("user", "I moved to Seattle."), ("assistant", "Nice!")])
    r = client.post("/add", json=body)
    assert r.status_code == 200
    resp = r.json()
    assert resp == {"success": True, "request_id": "req-1",
                    "user_id": body["user_id"], "session_id": body["session_id"]}


def test_add_multi_message_stored_with_deterministic_ids(client, tmp_path):
    body = add_payload("req-multi", "user-A", "sess-A",
                       [("user", "first"), ("user", "second"), ("assistant", "third")])
    assert client.post("/add", json=body).status_code == 200
    store = EvalStore(f"sqlite:///{(tmp_path / 'eval_test.db').as_posix()}")
    rows = store.memories_for_user("user-A")
    assert len(rows) == 3
    assert [r["msg_index"] for r in rows] == [0, 1, 2]
    assert [r["id"] for r in rows] == [mem_id("req-multi", i) for i in range(3)]
    assert [r["raw_content"] for r in rows] == ["first", "second", "third"]
    assert rows[0]["timestamp_ms"] is not None


def test_add_idempotent_same_request(client, tmp_path):
    body = add_payload("req-dup", "user-A", "sess-A",
                       [("user", "x"), ("assistant", "y")])
    r1 = client.post("/add", json=body)
    r2 = client.post("/add", json=body)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
    store = EvalStore(f"sqlite:///{(tmp_path / 'eval_test.db').as_posix()}")
    assert store.count_memories("user-A") == 2
    # duplicate also detected at store level
    status, n = store.add_batch("req-dup", "user-A", "sess-A",
                                [{"role": "user", "content": "x"}])
    assert (status, n) == ("duplicate", 0)


def test_add_validation_422(client):
    base = add_payload("req", "u", "s", [("user", "hi")])
    for drop in ("request_id", "user_id", "session_id"):
        bad = {k: v for k, v in base.items() if k != drop}
        assert client.post("/add", json=bad).status_code == 422, drop
    bad_msgs = dict(base)
    bad_msgs["messages"] = []
    assert client.post("/add", json=bad_msgs).status_code == 422
    bad_role = dict(base)
    bad_role["messages"] = [{"role": "system", "content": "hi"}]
    assert client.post("/add", json=bad_role).status_code == 422


def test_add_atomic_on_embed_failure(tmp_path):
    """Mid-batch embedding failure must leave ZERO rows (retry-safe)."""
    store = EvalStore(f"sqlite:///{(tmp_path / 'atomic.db').as_posix()}")

    def flaky(content):
        if content == "boom":
            raise RuntimeError("embed model down")
        return np.zeros(8, dtype=np.float32).tobytes()

    msgs = [{"role": "user", "content": "ok"},
            {"role": "user", "content": "boom"},
            {"role": "user", "content": "also ok"}]
    with pytest.raises(RuntimeError):
        store.add_batch("req-atomic", "u", "s", msgs, embed_fn=flaky)
    assert store.count_memories("u") == 0
    assert store.count_memories() == 0
    # clean retry succeeds
    status, n = store.add_batch("req-atomic", "u", "s", msgs)
    assert (status, n) == ("created", 3)


def test_ttl_cleanup(tmp_path):
    store = EvalStore(f"sqlite:///{(tmp_path / 'ttl.db').as_posix()}")
    store.add_batch("r1", "u", "s", [{"role": "user", "content": "old"}])
    with store.session() as db:
        old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
        db.query(AddRequest).filter(AddRequest.request_id == "r1") \
            .update({"completed_at": old}, synchronize_session=False)
        db.commit()
    deleted = store.ttl_cleanup(hours=24 * 30)
    assert deleted >= 1
    assert store.count_memories() == 0


# ── Search contract ────────────────────────────────────────────────────────

def test_search_empty_for_unknown_user(client):
    client.post("/add", json=add_payload("r1", "user-A", "s", [("user", "Seattle rain")]))
    r = client.post("/search", json={"query": "Seattle", "user_id": "user-B", "top_k": 100})
    assert r.status_code == 200
    assert r.json() == {"data": []}


def test_search_strict_user_isolation(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    client.post("/add", json=add_payload("rA", "user-A", "s",
                                         [("user", "Alice lives in Seattle")]))
    client.post("/add", json=add_payload("rB", "user-B", "s",
                                         [("user", "Alice lives in Beijing")]))
    # user-A can never see user-B rows, whatever the query says
    for query in ("Alice lives in Seattle", "Alice lives in Beijing"):
        r = client.post("/search", json={"query": query, "user_id": "user-A",
                                         "top_k": 100})
        contents = [h["content"] for h in r.json()["data"]]
        assert contents == ["Alice lives in Seattle"], query
    r = client.post("/search", json={"query": "Beijing", "user_id": "user-B",
                                     "top_k": 100})
    assert [h["content"] for h in r.json()["data"]] == ["Alice lives in Beijing"]


def test_envelope_content_and_created_at(client):
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [("user", "I moved to Seattle.")], ts_start=1_704_067_200_000))
    r = client.post("/search", json={"query": "I moved to Seattle", "user_id": "u1", "top_k": 5})
    hits = r.json()["data"]
    assert hits and hits[0]["content"] == \
        "[2024-01-01T00:00:00+00:00] user: I moved to Seattle."
    # created_at prefers the source timestamp
    assert hits[0]["created_at"] == "2024-01-01T00:00:00+00:00"


def test_envelope_off_returns_raw(client, monkeypatch):
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [("user", "I moved to Seattle.")], ts_start=1_704_067_200_000))
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    r = client.post("/search", json={"query": "moved to Seattle", "user_id": "u1", "top_k": 5})
    assert r.json()["data"][0]["content"] == "I moved to Seattle."


def test_envelope_without_timestamp(client, monkeypatch):
    monkeypatch.delenv("MINTA_EVAL_ENVELOPE", raising=False)
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [("user", "plain memory")], ts_start=None))
    r = client.post("/search", json={"query": "plain memory", "user_id": "u1", "top_k": 5})
    assert r.json()["data"][0]["content"] == "user: plain memory"


# ── retrieval mainline ─────────────────────────────────────────────────────

def test_dense_relevance_ordering(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    client.post("/add", json=add_payload(
        "r1", "u1", "s",
        [("user", "my favorite color is blue"),
         ("user", "I moved to Seattle in March"),
         ("user", "Seattle weather is rainy")]))
    r = client.post("/search", json={"query": "where do I live Seattle",
                                     "user_id": "u1", "top_k": 10})
    contents = [h["content"] for h in r.json()["data"]]
    assert contents[0] == "I moved to Seattle in March"


def test_neighbour_window_same_chunk_only(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_RADIUS", "1")
    client.post("/add", json=add_payload(
        "R1", "u1", "s",
        [("user", "sushi is delicious"),          # idx 0 — seed for query
         ("user", "we plan a sushi dinner"),      # idx 1 — neighbour
         ("user", "tokyo trip cancelled")]))      # idx 2 — far
    client.post("/add", json=add_payload(
        "R2", "u1", "s",
        [("user", "sushi again later")]))          # other chunk, same user
    r = client.post("/search", json={"query": "sushi", "user_id": "u1", "top_k": 4})
    ids = [h["id"] for h in r.json()["data"]]
    # neighbour of R1:0 is R1:1 (idx -1 does not exist, must not jump to R2)
    assert mem_id("R1", 0) in ids
    assert mem_id("R1", 1) in ids


def test_neighbour_window_radius_zero(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_RADIUS", "0")
    client.post("/add", json=add_payload(
        "R1", "u1", "s",
        [("user", "sushi is delicious"),
         ("user", "we plan a sushi dinner")]))
    r = client.post("/search", json={"query": "sushi", "user_id": "u1", "top_k": 1})
    ids = [h["id"] for h in r.json()["data"]]
    assert ids == [mem_id("R1", 0)]  # exactly top_k, no expansion


def test_top_k_fill_and_cap(client):
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [(r, f"message number {i}") for i in range(5) for r in ("user",)]))
    r = client.post("/search", json={"query": "message", "user_id": "u1", "top_k": 3})
    assert len(r.json()["data"]) == 3
    r100 = client.post("/search", json={"query": "message", "user_id": "u1", "top_k": 100})
    assert len(r100.json()["data"]) == 5  # fill up to what exists


def test_dedupe_suppression_at_retrieval(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [("user", "exact duplicate text"), ("user", "other note")]))
    client.post("/add", json=add_payload(
        "r2", "u1", "s", [("user", "exact duplicate text")]))
    r = client.post("/search", json={"query": "exact duplicate text", "user_id": "u1",
                                     "top_k": 100})
    contents = [h["content"] for h in r.json()["data"]]
    assert contents.count("exact duplicate text") == 1  # suppressed, not lost


def test_search_empty_query_422(client):
    assert client.post("/search", json={"query": "", "user_id": "u", "top_k": 10}
                       ).status_code == 422


# ── experiment arms (env-gated, all default off) ───────────────────────────

def test_options_expansion_off_by_default(client, monkeypatch):
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    monkeypatch.delenv("MINTA_EVAL_OPTIONS", raising=False)
    client.post("/add", json=add_payload(
        "r1", "u1", "s",
        [("user", "I prefer tea over coffee"),   # idx 0 (older)
         ("user", "I prefer coffee every morning")]))  # idx 1 (newer)
    r = client.post("/search", json={
        "query": "Which drink does the user prefer?",
        "options": ["A. tea", "B. coffee"],
        "user_id": "u1", "top_k": 5})
    # no overlap between query and docs -> recency fallback -> newest first
    assert "coffee every morning" in r.json()["data"][0]["content"]


def test_options_expansion_on_widens_evidence(client, monkeypatch):
    """The arm widens recall to option-relevant evidence (never judges)."""
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    monkeypatch.setenv("MINTA_EVAL_OPTIONS", "1")
    client.post("/add", json=add_payload(
        "r1", "u1", "s",
        [("user", "she drinks tea leaves"),        # idx 0
         ("user", "she brews coffee beans"),       # idx 1
         ("user", "she hikes mountain trails")]))  # idx 2 (newest, unrelated)
    r = client.post("/search", json={
        "query": "Which topic is discussed most often?",
        "options": ["A. tea", "B. coffee"],
        "user_id": "u1", "top_k": 5})
    hits = r.json()["data"]
    # tea/coffee memories get option-driven scores > 0; the query itself has
    # zero overlap with any memory, so the unrelated newest stays at 0.0
    assert hits[0]["content"] in ("she drinks tea leaves", "she brews coffee beans")
    assert hits[1]["content"] in ("she drinks tea leaves", "she brews coffee beans")
    assert hits[0]["score"] is not None and hits[0]["score"] > 0
    assert hits[-1]["content"] == "she hikes mountain trails"
    assert hits[-1]["score"] == 0.0


def test_recall_query_offline_degrades_gracefully(client, monkeypatch):
    """RECALL_QUERY on but LLM endpoint down -> channel skipped, still 200."""
    monkeypatch.setenv("MINTA_EVAL_RECALL_QUERY", "1")
    monkeypatch.setenv("MINTA_EVAL_LLM_BASE", "http://127.0.0.1:9")
    monkeypatch.setenv("MINTA_EVAL_LLM_KEY", "test-key")
    monkeypatch.setenv("MINTA_EVAL_ENVELOPE", "off")
    client.post("/add", json=add_payload(
        "r1", "u1", "s", [("user", "sushi in tokyo is great")]))
    r = client.post("/search", json={"query": "sushi", "user_id": "u1", "top_k": 5})
    assert r.status_code == 200
    assert r.json()["data"][0]["content"] == "sushi in tokyo is great"
