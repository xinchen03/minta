"""Conflict-detector taxonomy regression tests.

Gate 0.5: same-content pairs (cos ≥ DUPLICATE_COS) must be classified as
duplicates (D_V/redundancy business), never as conflict — even when a
negation keyword trips the bypass. Real negation-contrast pairs with
cos < DUPLICATE_COS must still be flagged.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

os.environ["MINTA_ENV"] = "development"

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from services.conflict_detector import detect_conflicts, DUPLICATE_COS  # noqa: E402


def _obj(obj_id, title, summary, vec):
    return {
        "id": obj_id,
        "title": title,
        "summary": summary,
        "body": "",
        "embedding_384": json.dumps(vec),
        "created_at": datetime.now(timezone.utc),
        "last_used_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "confidence": 4,
        "type": "preference",
        "status": "active",
    }


def test_duplicate_threshold_is_sane():
    assert DUPLICATE_COS == 0.995


def test_identical_pair_with_negation_word_not_conflict():
    """Regression: '不'/'不是' inside identical content used to trip the
    negation bypass and re-flag the pair as an ambiguous conflict (P=σ(γ)
    base rate, observed: 0.599 vs θ_c=0.46)."""
    vec = [1.0, 0.0, 0.0, 0.0]
    a = _obj("a", "gage线不是永久偏好", "measurement line, not a permanent preference", vec)
    b = _obj("b", "gage线不是永久偏好", "measurement line, not a permanent preference", vec)
    assert detect_conflicts([a, b], graph_edges=[]) == []


def test_real_negation_contrast_still_flagged():
    """Same topic, opposite instructions (b_ij=1), cos below the duplicate
    threshold → must still surface as a conflict."""
    a = _obj("a", "keep the danger axis",
             "preferred pick: keep the danger axis inside the candidate set",
             [1.0, 0.0, 0.0, 0.0])
    b = _obj("b", "do not keep the danger axis",
             "preferred pick: do not keep the danger axis in the candidate set",
             [0.85, 0.15, 0.0, 0.0])
    findings = detect_conflicts([a, b], graph_edges=[])
    assert len(findings) == 1, findings
    assert findings[0]["type"] == "conflict"


def test_unrelated_pairs_no_conflict():
    a = _obj("a", "rain today", "the day brings rain", [1.0, 0.0, 0.0, 0.0])
    b = _obj("b", "night sky", "stars visible at night", [0.0, 1.0, 0.0, 0.0])
    assert detect_conflicts([a, b], graph_edges=[]) == []
