"""User-data export/delete inventory tests.

Every user-scoped category must appear in /api/user/export-data and be
purged by /api/user/delete-data: DB tables, Chroma vectors (via the
embedding service), Autopilot JSONL logs, and credentials (revoked, never
exported). Env must be set BEFORE the app import (same rule as
test_main_search).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

os.environ["MINTA_ENV"] = "development"
os.environ["MINTA_DATABASE_URL"] = "sqlite:///" + tempfile.mkdtemp(
    prefix="minta_userdata_test_").replace(os.sep, "/") + "/ud.db"
os.environ["MINTA_EVAL_DB"] = "sqlite:///" + tempfile.mkdtemp(
    prefix="minta_userdata_eval_test_").replace(os.sep, "/") + "/eval.db"
os.environ["MINTA_EMBEDDING_ENABLED"] = "1"

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)


class FakeEmbeddingService:
    """Deterministic stand-in; captures delete_user calls."""

    def __init__(self):
        self.deleted_users = []

    def delete_user(self, user_id):
        self.deleted_users.append(str(user_id))
        return 3  # pretend 3 vectors removed

    def export_user(self, user_id):
        return [{"id": "vec-1", "metadata": {"user_id": str(user_id)}}]

    def add_vector(self, *args, **kwargs):
        pass

    def delete_vectors(self, ids):
        pass

    def search(self, *args, **kwargs):
        return []

    def _ensure_init(self):
        pass


_fake = FakeEmbeddingService()
import services.embedding_service as _es_mod  # noqa: E402

from main import app  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from config import get_db  # noqa: E402
from models.inbox import InboxItem  # noqa: E402
from models.skill import Skill  # noqa: E402
from models.slot import Slot  # noqa: E402
from models.api_key import ApiKey  # noqa: E402
from models.session import Session as ProjectSession  # noqa: E402
from models.activity_log import ActivityLog  # noqa: E402
from models.graph_edge import GraphEdge  # noqa: E402
from routers.comments import Comment  # noqa: E402
from services.autopilot import decision_logger  # noqa: E402
from eval_store import EvalStore  # noqa: E402
import routers.user_data as user_data_router  # noqa: E402

CLIENT = None


def _client():
    global CLIENT
    if CLIENT is None:
        CLIENT = TestClient(app)
    return CLIENT


@pytest.fixture(autouse=True)
def _patch_embedding(monkeypatch):
    # per-test patch (restored after each test) — a module-level patch here
    # would clobber test_main_search's, which patches the same attribute.
    monkeypatch.setattr(_es_mod, "get_embedding_service", lambda: _fake)
    yield
    _fake.deleted_users.clear()


@pytest.fixture(autouse=True)
def _fresh_logs(tmp_path):
    decision_logger.LOG_DIR = str(tmp_path / "logs")
    yield


def _register(name: str, headers_out: dict) -> int:
    c = _client()
    r = c.post("/api/auth/register", json={
        "username": name, "email": f"{name}@test.local", "password": "pw-123456"})
    assert r.status_code == 200, r.text
    uid = int(r.json()["id"])
    r = c.post("/api/auth/login", json={"username": name, "password": "pw-123456"})
    assert r.status_code == 200, r.text
    headers_out.update({"Authorization": "Bearer " + r.json()["accessToken"]})
    return uid


def _seed(uid: int) -> None:
    """One row per representative category + a second (other) user's row."""
    db = next(get_db())
    try:
        db.add(InboxItem(user_id=uid, text="inbox-1", type="preference"))
        db.add(InboxItem(user_id=uid, text="inbox-2"))
        db.add(Skill(id=f"skill-{uid}", user_id=uid, name="X", name_zh="Y", group="g"))
        db.add(Slot(user_id=uid, label="identity", content="the user"))
        db.add(ActivityLog(user_id=uid, event_type="login", detail="x"))
        db.add(GraphEdge(user_id=uid, context_id_a="a", context_id_b="b"))
        db.add(Comment(object_id="obj-1", user_id=uid, username="tester", content="c"))
        db.add(ApiKey(user_id=uid, key_prefix="minta_ab1", key_hash="h", name="t"))
        db.add(ProjectSession(
            id=f"sess-{uid}", user_id=uid, project_path="project/redacted",
            observation_count=2, correction_count=1, summary="session summary"))
        # isolation probe: another user's row must survive the deletion
        db.add(InboxItem(user_id=1000 + uid, text="other-user-inbox"))
        db.commit()
    finally:
        db.close()
    decision_logger.write_log({"user_id": str(uid), "phase": "preflight", "summary": "secret text"})
    decision_logger.write_log({"user_id": "other", "phase": "preflight", "summary": "keep me"})
    EvalStore().add_batch(
        f"req-{uid}", str(uid), f"eval-session-{uid}",
        [{"role": "user", "content": "eval memory", "timestamp": 1700000000000}],
    )


# ── export ────────────────────────────────────────────────────────────────
def test_export_covers_every_category():
    h = {}
    uid = _register("export_user", h)
    _seed(uid)
    r = _client().get("/api/user/export-data", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    for label in ("contextObjects", "inboxItems", "skills", "slots", "graphEdges",
                  "archivedItems", "activityLog", "inferenceLog", "contextRetrievalLog",
                  "taskRewardLog", "banditState", "comments", "auditLog", "sessions",
                  "autopilotLogs", "evalData", "vectors", "avatar"):
        assert label in d, "export missing category: %s" % label
    texts = {i["text"] for i in d["inboxItems"]}
    assert {"inbox-1", "inbox-2"} <= texts
    assert "the user" in {s["content"] for s in d["slots"]}
    assert d["autopilotLogs"] and d["autopilotLogs"][0]["user_id"] == str(uid)
    assert d["sessions"][0]["summary"] == "session summary"
    assert d["evalData"]["memories"][0]["raw_content"] == "eval memory"
    assert d["vectors"][0]["metadata"]["user_id"] == str(uid)
    # credentials are never exported
    assert "apiKeys" not in d, "API key material must not be exported"


# ── delete ────────────────────────────────────────────────────────────────
def test_delete_purges_all_categories():
    h = {}
    uid = _register("del_user", h)
    _seed(uid)
    r = _client().delete("/api/user/delete-data", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    d = body["deleted"]
    for label in ("contextObjects", "inboxItems", "skills", "slots", "graphEdges",
                  "archivedItems", "activityLog", "inferenceLog", "contextRetrievalLog",
                  "taskRewardLog", "banditState", "comments", "auditLog", "apiKeys",
                  "sessions"):
        assert label in d, "delete missing category: %s" % label
    # the seed writes exactly one row per controlled category
    assert d["skills"] >= 1 and d["slots"] >= 1 and d["inboxItems"] >= 2
    assert d["activityLog"] >= 1
    assert d["graphEdges"] == 1
    assert d["comments"] == 1
    assert d["apiKeys"] == 1 and d["sessions"] >= 1
    assert d["vectors"] == 3 and d["autopilotLogs"] == 1
    assert _fake.deleted_users == [str(uid)]

    # data really gone; other user's data intact (isolation)
    db = next(get_db())
    try:
        assert db.query(InboxItem).filter(InboxItem.user_id == uid).count() == 0
        assert db.query(Slot).filter(Slot.user_id == uid).count() == 0
        assert db.query(Skill).filter(Skill.user_id == uid).count() == 0
        assert db.query(ApiKey).filter(ApiKey.user_id == uid).count() == 0
        assert db.query(ProjectSession).filter(ProjectSession.user_id == uid).count() == 0
        assert db.query(ActivityLog).filter(ActivityLog.user_id == uid).count() == 0
        assert db.query(Comment).filter(Comment.user_id == uid).count() == 0
        assert db.query(InboxItem).filter(InboxItem.user_id == 1000 + uid).count() == 1
    finally:
        db.close()

    # autopilot jsonl: our user's entries removed, other user's kept
    kept_other = 0
    for root, _, files in os.walk(decision_logger.LOG_DIR):
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8") as f:
                for line in f:
                    e = json.loads(line)
                    if str(e.get("user_id")) == "other":
                        kept_other += 1
    assert kept_other == 1
    assert EvalStore().count_memories(str(uid)) == 0


# ── idempotent second run ─────────────────────────────────────────────────
def test_delete_is_idempotent():
    h = {}
    uid = _register("idem_user", h)
    _seed(uid)
    _client().delete("/api/user/delete-data", headers=h)
    r = _client().delete("/api/user/delete-data", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_delete_commits_successful_categories_when_one_table_fails(monkeypatch):
    h = {}
    uid = _register("partial_user", h)
    _seed(uid)
    original = user_data_router._purge_table

    def fail_skills(db, model, user_id):
        if model is Skill:
            raise RuntimeError("forced category failure")
        return original(db, model, user_id)

    monkeypatch.setattr(user_data_router, "_purge_table", fail_skills)
    r = _client().delete("/api/user/delete-data", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False and body["partial"] is True
    assert "skills" in body["errors"]

    db = next(get_db())
    try:
        assert db.query(InboxItem).filter(InboxItem.user_id == uid).count() == 0
        assert db.query(Slot).filter(Slot.user_id == uid).count() == 0
        assert db.query(Skill).filter(Skill.user_id == uid).count() == 1
    finally:
        db.close()
