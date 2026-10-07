"""Tests for correction propagation in services/reflect.py.

Covers the English path used by public-repo users: confirming a correction
must (a) knock down overlapping memories (tagged "countered") and (b) surface
the correction in the counter_examples slot ("Recent Lessons" in the pack).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("MINTA_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Base  # noqa: E402
from models.context_object import ContextObject  # noqa: E402
from models.inbox import InboxItem  # noqa: E402
from models.slot import Slot  # noqa: E402
from services.reflect import (  # noqa: E402
    _apply_counter_to_context,
    detect_signals,
    record_correction,
    route_to_slot,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database per test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _add_context(db, *, id, title, body, user_id=1, confidence=4,
                 context_type="project_context") -> ContextObject:
    obj = ContextObject(
        id=id,
        user_id=user_id,
        type=context_type,
        title=title,
        summary="",
        body=body,
        tags=[],
        source="manual",
        status="active",
        confidence=confidence,
        updated_at=_utcnow(),
        last_used_at=None,
    )
    db.add(obj)
    db.commit()
    return obj


def _add_slot(db, label, user_id=1):
    db.add(Slot(user_id=user_id, label=label, content="", size_limit=2000))
    db.commit()


# ── Signal detection ──

def test_english_correction_signal_detected():
    signals = detect_signals(
        "Correction: we no longer use PostgreSQL for the database.")
    assert any(s["type"] == "correction" for s in signals)


def test_english_memory_update_signal_detected():
    signals = detect_signals(
        "The server port changed to 8772 in the last deploy.")
    assert any(s["type"] == "correction" for s in signals)


def test_chinese_correction_signal_still_detected():
    signals = detect_signals("不对，端口应该是 8772，不是 8000。")
    assert any(s["type"] == "correction" for s in signals)


# ── Counter application (knock-down) ──

def test_english_overlap_knocks_down_and_tags(db_session):
    db = db_session
    _add_context(db, id="db-notes", title="Database notes",
                 body="The project database is PostgreSQL, hosted on server X.")
    _add_context(db, id="gym-log", title="Gym log",
                 body="Squats and deadlifts on Tuesday.", context_type="task_note")

    affected = _apply_counter_to_context(
        db, 1, "We no longer use PostgreSQL; the database moved to MySQL.")

    assert affected == 1
    old = db.query(ContextObject).filter_by(id="db-notes").first()
    assert old.confidence == 2
    assert "countered" in (old.tags or [])
    gym = db.query(ContextObject).filter_by(id="gym-log").first()
    assert gym.confidence == 4
    assert "countered" not in (gym.tags or [])


def test_exclude_ids_skips_the_confirmed_object(db_session):
    db = db_session
    _add_context(db, id="self-note", title="Self",
                 body="The project database is PostgreSQL on server X.")

    affected = _apply_counter_to_context(
        db, 1, "We no longer use PostgreSQL for the database.",
        exclude_ids={"self-note"})

    assert affected == 0
    note = db.query(ContextObject).filter_by(id="self-note").first()
    assert note.confidence == 4


# ── record_correction (full propagation) ──

def test_record_correction_writes_recent_lesson_slot(db_session):
    db = db_session
    _add_slot(db, "counter_examples")
    _add_context(db, id="db-notes", title="Database notes",
                 body="The project database is PostgreSQL, hosted on server X.")

    result = record_correction(
        db, 1,
        "Correction: the database moved to MySQL, we no longer use PostgreSQL.",
        exclude_ids={"self-new"})

    assert result["detected"] is True
    assert result["affected"] == 1
    assert result["slot_updated"] is True
    slot = db.query(Slot).filter_by(user_id=1, label="counter_examples").first()
    assert "PostgreSQL" in slot.content
    assert slot.auto_reflected is True


def test_record_correction_ignores_non_corrections(db_session):
    db = db_session
    _add_context(db, id="db-notes", title="Database notes",
                 body="The project database is PostgreSQL, hosted on server X.")

    result = record_correction(
        db, 1, "Reminder: check the deployment dashboard tomorrow.")

    assert result["detected"] is False
    assert result["affected"] == 0
    old = db.query(ContextObject).filter_by(id="db-notes").first()
    assert old.confidence == 4


# ── route_to_slot regression guard (extracted via _append_to_slot) ──

def test_route_to_slot_still_writes_correction_slot(db_session):
    db = db_session
    _add_slot(db, "counter_examples")

    label, applied = route_to_slot(db, 1, "correction", "[auto] 不对，端口应该是 8772")

    assert label == "counter_examples"
    assert applied is True
    slot = db.query(Slot).filter_by(user_id=1, label="counter_examples").first()
    assert "8772" in slot.content


# ── Inbox confirm wiring (the reachable moment for public users) ──

def test_confirm_endpoint_propagates_correction(db_session, monkeypatch):
    from services import vector_ops
    from routers.inbox import confirm_item

    monkeypatch.setattr(vector_ops, "apply_conflict_embedding", lambda obj: None)
    monkeypatch.setattr(vector_ops, "index_object", lambda *a, **k: None)

    db = db_session
    _add_slot(db, "counter_examples")
    _add_context(db, id="db-notes", title="Database notes",
                 body="The project database is PostgreSQL, hosted on server X.")
    item = InboxItem(
        user_id=1,
        text="Correction: the database moved to MySQL, we no longer use PostgreSQL.",
        confidence=0.9,
        status="pending",
        tags=[],
    )
    db.add(item)
    db.commit()

    result = confirm_item(item.id, {"type": "lesson_learned"},
                          SimpleNamespace(id=1), db)

    assert result["success"] is True
    old = db.query(ContextObject).filter_by(id="db-notes").first()
    assert old.confidence == 2
    assert "countered" in (old.tags or [])

    new_obj = db.query(ContextObject).filter_by(id=result["contextId"]).first()
    assert new_obj is not None
    assert "countered" not in (new_obj.tags or [])


def test_archive_endpoint_propagates_correction(db_session, monkeypatch):
    from services import vector_ops
    from routers.inbox import archive_items

    monkeypatch.setattr(vector_ops, "apply_conflict_embedding", lambda obj: None)
    monkeypatch.setattr(vector_ops, "index_object", lambda *a, **k: None)

    db = db_session
    _add_slot(db, "counter_examples")
    _add_context(db, id="db-notes", title="Database notes",
                 body="The project database is PostgreSQL, hosted on server X.")
    item = InboxItem(
        user_id=1,
        text="Correction: the database moved to MySQL, we no longer use PostgreSQL.",
        confidence=0.9,
        status="pending",
        tags=[],
    )
    db.add(item)
    db.commit()

    result = archive_items(
        {"ids": [item.id], "types": {str(item.id): "lesson_learned"}},
        SimpleNamespace(id=1), db,
    )

    assert result["success"] is True
    old = db.query(ContextObject).filter_by(id="db-notes").first()
    assert old.confidence == 2
    assert "countered" in (old.tags or [])
