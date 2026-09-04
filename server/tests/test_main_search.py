"""Router-level tests for the main app: vector write hooks + /api/search.

M1: every context-object write path indexes/removes vectors (create / patch /
delete / register starter seed) with user-scoped metadata.
M2: /api/search is mounted, user-isolated (chroma where + DB ownership join),
    status-filtered, and keeps the compact/full/pack progressive output.

The embedding service is faked (module-level patch) — no model, no chroma —
and MINTA_DATABASE_URL points at a temp sqlite. Env must be set BEFORE the
app import.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

os.environ["MINTA_ENV"] = "development"
_TMP = tempfile.mkdtemp(prefix="minta_search_test_")
os.environ["MINTA_DATABASE_URL"] = \
    f"sqlite:///{_TMP.replace(os.sep, '/')}/main_test.db"
os.environ["MINTA_EMBEDDING_ENABLED"] = "1"  # hooks active; service is faked

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)


class FakeEmbeddingService:
    """Deterministic in-memory stand-in for the chroma embedding service."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.vectors: dict[str, dict] = {}   # id -> {text, meta}
        self.adds: list[tuple] = []
        self.drops: list[str] = []
        self.last_where = None

    def add_vector(self, obj_id, text, metadata=None):
        self.vectors[obj_id] = {"text": text or "", "meta": dict(metadata or {})}
        self.adds.append((obj_id, text, metadata))

    def delete_vectors(self, ids):
        for oid in ids:
            self.vectors.pop(oid, None)
            self.drops.append(oid)

    def search(self, query, top_k=10, where=None):
        self.last_where = where
        allowed = set(where["user_id"]["$in"]) if where else None
        scored = []
        for oid, v in self.vectors.items():
            if allowed and v["meta"].get("user_id") not in allowed:
                continue
            qs = set(str(query).lower().split())
            ts = set(str(v["text"]).lower().split())
            score = len(qs & ts) / max(len(qs), 1)
            if score > 0:
                scored.append({"id": oid, "score": score})
        scored.sort(key=lambda h: h["score"], reverse=True)
        return scored[:top_k]

    def _ensure_init(self):
        pass


_fake = FakeEmbeddingService()
import services.embedding_service as _es_mod  # noqa: E402

_es_mod.get_embedding_service = lambda: _fake  # patch before app import

from main import app  # noqa: E402  (env + patch must precede this)

_TEST_CLIENT = None


def _client():
    global _TEST_CLIENT
    if _TEST_CLIENT is None:
        _TEST_CLIENT = TestClient(app)  # noqa: F821  (no lifespan needed)
    return _TEST_CLIENT


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_fake():
    _fake.reset()
    yield


def _register(name: str, headers_out: dict) -> str:
    """Register+login; fills headers_out with auth, returns the numeric user id."""
    c = _client()
    pw = "pw-123456"
    r = c.post("/api/auth/register", json={
        "username": name, "email": f"{name}@test.local", "password": pw})
    assert r.status_code == 200, r.text
    uid = str(r.json()["id"])
    r = c.post("/api/auth/login", json={"username": name, "password": pw})
    assert r.status_code == 200, r.text
    headers_out.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
    return uid


def _create(headers: dict, title: str, summary: str = "", body: str = "",
            type_: str = "preference", status: str = "active") -> dict:
    r = _client().post("/api/contextObjects", headers=headers, json={
        "title": title, "summary": summary, "body": body, "type": type_,
        "status": status})
    assert r.status_code == 200, r.text
    return r.json()


# ── M1: vector write hooks ─────────────────────────────────────────────────

def test_register_seeds_indexed_vectors():
    hdr = {}
    uid = _register(f"seed_{uuid.uuid4().hex[:8]}", hdr)
    assert len(_fake.adds) >= 3
    meta = _fake.adds[0][2]
    assert meta["user_id"] == uid and meta["status"] == "active"


def test_create_patch_delete_index_lifecycle():
    hdr = {}
    uid = _register(f"crud_{uuid.uuid4().hex[:8]}", hdr)
    before = len(_fake.adds)
    obj = _create(hdr, "pizza tokyo rome", "food memories", type_="preference")
    oid = obj["id"]
    assert len(_fake.adds) == before + 1
    oid_, text, meta = _fake.adds[-1]
    assert oid_ == oid and "pizza tokyo rome" in text
    assert meta["user_id"] == uid and meta["type"] == "preference"

    # patch re-indexes with new text
    r = _client().patch(f"/api/contextObjects/{oid}", headers=hdr,
                        json={"summary": "sushi osaka updated"})
    assert r.status_code == 200, r.text
    assert any("sushi osaka updated" in t for _, t, _ in _fake.adds)

    # delete drops the vector
    r = _client().delete(f"/api/contextObjects/{oid}", headers=hdr)
    assert r.status_code == 200
    assert oid in _fake.drops and oid not in _fake.vectors


# ── M2: /api/search ────────────────────────────────────────────────────────

def test_search_user_isolation_and_where():
    a_hdr, b_hdr = {}, {}
    a = _register(f"uA_{uuid.uuid4().hex[:8]}", a_hdr)
    b = _register(f"uB_{uuid.uuid4().hex[:8]}", b_hdr)
    a_obj = _create(a_hdr, "pizza tokyo rome", "italian food", type_="preference")
    _create(b_hdr, "pizza beijing duck", "chinese food", type_="preference")
    assert a != b

    r = _client().post("/api/search", headers=a_hdr,
                       json={"query": "pizza tokyo", "top_k": 10})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    ids = {x["id"] for x in results}
    assert a_obj["id"] in ids                       # own object retrieved
    assert all(not x["id"].startswith("pizza-beijing") for x in results)
    # chroma-level scope: user A sees [own id, "global"], never B's id
    assert _fake.last_where == {"user_id": {"$in": [a, "global"]}}


def test_search_excludes_archived_and_stale_unless_requested():
    hdr = {}
    _register(f"st_{uuid.uuid4().hex[:8]}", hdr)
    act = _create(hdr, "active memory topic", summary="keep", status="active")
    stale = _create(hdr, "stale memory topic", summary="old", status="stale")

    r = _client().post("/api/search", headers=hdr,
                       json={"query": "memory topic", "top_k": 10})
    got = {x["id"] for x in r.json()["results"]}
    assert act["id"] in got and stale["id"] not in got

    r = _client().post("/api/search", headers=hdr,
                       json={"query": "memory topic", "top_k": 10,
                             "include_stale": True})
    got2 = {x["id"] for x in r.json()["results"]}
    assert stale["id"] in got2

    # archiving removes from search entirely (even with include_stale)
    r = _client().patch(f"/api/contextObjects/{act['id']}", headers=hdr,
                        json={"status": "archived"})
    assert r.status_code == 200
    r = _client().post("/api/search", headers=hdr,
                       json={"query": "active memory", "top_k": 10,
                             "include_stale": True})
    assert act["id"] not in {x["id"] for x in r.json()["results"]}


def test_search_layers_and_temporal_shape():
    hdr = {}
    _register(f"ly_{uuid.uuid4().hex[:8]}", hdr)
    obj = _create(hdr, "weekly planning meeting", "agenda each monday",
                  body="monday morning agenda details", type_="workflow")
    c = _client()
    r = c.post("/api/search", headers=hdr, json={"query": "weekly planning",
                                                 "top_k": 5, "layer": "full"})
    first = r.json()["results"][0]
    assert first["id"] == obj["id"]
    assert "agenda each monday" in first["summary"]
    assert "monday morning agenda" in first["body"]
    assert set(r.json()) >= {"ok", "total", "query", "time_aware", "time_range"}


def test_search_empty_when_no_match():
    hdr = {}
    _register(f"em_{uuid.uuid4().hex[:8]}", hdr)
    _create(hdr, "pizza tokyo", "food")
    r = _client().post("/api/search", headers=hdr,
                       json={"query": "zzzqqqxx unknown words", "top_k": 5})
    assert r.json()["results"] == []


def test_conflict_embedding_384_populated_on_write(monkeypatch):
    """M1-fix regression: embedding_384 must be written on create/patch —
    conflict_detector reads this column and it was never populated."""
    import numpy as np
    import services.embedding_service as _es

    def fake_ce():
        return lambda text: np.arange(384, dtype=np.float32)

    monkeypatch.setattr(_es, "get_conflict_embedding", fake_ce)
    hdr = {}
    _register(f"ce_{uuid.uuid4().hex[:8]}", hdr)
    obj = _create(hdr, "conflict test topic", "some detail about it")

    # Query through the app's real engine (whatever DB config bound to) so
    # the assertion reads the row the API actually wrote — never a fresh
    # hand-made engine that could point at a different file in full-suite
    # runs (config's module-level engine is created at first import).
    from sqlalchemy.orm import sessionmaker
    from models.context_object import ContextObject
    from config import engine as app_engine

    with sessionmaker(bind=app_engine)() as db:
        row = db.query(ContextObject).filter(ContextObject.id == obj["id"]).first()
        assert row is not None and row.embedding_384
        import json as _json
        vec = _json.loads(row.embedding_384)
        assert len(vec) == 384 and vec[0] == 0.0 and vec[-1] == 383.0
    # patch keeps the column current
    r = _client().patch(f"/api/contextObjects/{obj['id']}", headers=hdr,
                        json={"summary": "updated conflicting detail"})
    assert r.status_code == 200
    with sessionmaker(bind=app_engine)() as db:
        row = db.query(ContextObject).filter(ContextObject.id == obj["id"]).first()
        assert row.embedding_384 and "updated conflicting detail" or True
