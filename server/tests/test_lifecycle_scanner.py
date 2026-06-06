"""Unit tests for lifecycle_scanner.py edge cases."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("MINTA_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Base  # noqa: E402
from models.context_object import ContextObject  # noqa: E402
from services.lifecycle_scanner import (  # noqa: E402
    FRAGMENT_MIN_COUNT,
    REDUNDANCY_RATIO,
    STALE_DAYS,
    findings_to_inbox_items,
    run_full_scan,
    scan_conflict,
    scan_fragmentation,
    scan_redundancy,
    scan_schema_validation,
    scan_staleness,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database for scanner tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _add_context(
    db,
    *,
    id: str,
    title: str,
    user_id: int = 1,
    summary: str = "summary",
    body: str | None = "body",
    tags: list[str] | None = None,
    context_type: str = "preference",
    status: str = "active",
    updated_at: datetime | None = None,
    last_used_at: datetime | None = None,
    confidence: int = 3,
) -> ContextObject:
    obj = ContextObject(
        id=id,
        user_id=user_id,
        type=context_type,
        title=title,
        summary=summary,
        body=body,
        tags=tags or [],
        source="manual",
        status=status,
        confidence=confidence,
        updated_at=updated_at or _utcnow(),
        last_used_at=last_used_at,
    )
    db.add(obj)
    db.commit()
    return obj


def test_recently_used_context_is_not_stale(db_session):
    _add_context(
        db_session,
        id="recent",
        title="Recently used preference",
        updated_at=_utcnow() - timedelta(days=STALE_DAYS + 10),
        last_used_at=_utcnow() - timedelta(days=1),
    )

    assert scan_staleness(db_session, user_id=1) == []


def test_old_never_used_context_is_flagged_stale(db_session):
    _add_context(
        db_session,
        id="stale",
        title="Old preference",
        updated_at=_utcnow() - timedelta(days=STALE_DAYS + 1),
        last_used_at=None,
    )

    findings = scan_staleness(db_session, user_id=1)

    assert len(findings) == 1
    assert findings[0]["object_id"] == "stale"
    assert findings[0]["type"] == "staleness"


def test_redundancy_flags_similarity_boundary(db_session):
    _add_context(db_session, id="a", title="abcdefghij", summary="alpha")
    _add_context(db_session, id="b", title="abcdefghxy", summary="beta")

    findings = scan_redundancy(db_session, user_id=1)

    assert REDUNDANCY_RATIO == 0.80
    assert len(findings) == 1
    assert findings[0]["similarity"] == 0.8
    assert findings[0]["object_ids"] == ["b", "a"]


def test_redundancy_ignores_below_boundary(db_session):
    _add_context(db_session, id="a", title="abcdefghij", summary="alpha")
    _add_context(db_session, id="b", title="abcdefwxyz", summary="beta")

    assert scan_redundancy(db_session, user_id=1) == []


def test_fragmentation_does_not_flag_below_threshold(db_session):
    for index in range(FRAGMENT_MIN_COUNT - 1):
        _add_context(
            db_session,
            id=f"tagged-{index}",
            title=f"Tagged context {index}",
            tags=["project-x"],
        )

    assert scan_fragmentation(db_session, user_id=1) == []


def test_fragmentation_flags_threshold_tag_count(db_session):
    for index in range(FRAGMENT_MIN_COUNT):
        _add_context(
            db_session,
            id=f"tagged-{index}",
            title=f"Tagged context {index}",
            tags=["project-x"],
        )

    findings = scan_fragmentation(db_session, user_id=1)

    assert len(findings) == 1
    assert findings[0]["tag"] == "project-x"
    assert findings[0]["object_count"] == FRAGMENT_MIN_COUNT


def test_non_conflicting_recommendations_are_not_flagged(db_session):
    _add_context(
        db_session,
        id="first",
        title="Python scripts",
        summary="Python handles automation jobs",
        tags=["automation"],
    )
    _add_context(
        db_session,
        id="second",
        title="Python batch jobs",
        summary="Python handles scheduled automation",
        tags=["automation"],
    )
    _add_context(
        db_session,
        id="third",
        title="Keep notes short",
        summary="Prefer short summaries",
        tags=["writing"],
    )

    assert scan_conflict(db_session, user_id=1) == []


def test_conflicting_recommendation_is_flagged(db_session):
    _add_context(
        db_session,
        id="prefer",
        title="Use SQLite",
        summary="Use SQLite for local storage",
        tags=["database"],
    )
    _add_context(
        db_session,
        id="avoid",
        title="Avoid SQLite",
        summary="Avoid SQLite for local storage",
        tags=["database"],
    )
    _add_context(
        db_session,
        id="other",
        title="Keep logs concise",
        summary="Use short operational logs",
        tags=["logging"],
    )

    findings = scan_conflict(db_session, user_id=1)

    assert len(findings) == 1
    assert findings[0]["type"] == "conflict"
    assert set(findings[0]["object_ids"]) == {"prefer", "avoid"}


def test_empty_database_full_scan_has_no_findings(db_session):
    findings = run_full_scan(db_session, user_id=1)

    assert findings == {
        "staleness": [],
        "redundancy": [],
        "fragmentation": [],
        "conflict": [],
        "schema_violation": [],
    }


def test_schema_validation_flags_empty_context(db_session):
    _add_context(
        db_session,
        id="empty",
        title="Empty context",
        summary="",
        body="",
    )

    findings = scan_schema_validation(db_session, user_id=1)

    assert len(findings) == 1
    assert findings[0]["object_id"] == "empty"
    assert findings[0]["violations"] == ["empty_body"]


def test_findings_convert_to_inbox_items():
    findings = {
        "staleness": [
            {
                "severity": "medium",
                "suggestion": "Review old memory",
            }
        ]
    }

    items = findings_to_inbox_items(findings, user_id=42)

    assert items == [
        {
            "user_id": 42,
            "text": "Review old memory",
            "type": "lesson_learned",
            "confidence": 0.6,
            "tags": ["lifecycle", "staleness", "auto-detected"],
            "status": "pending",
        }
    ]
