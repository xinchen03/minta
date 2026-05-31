"""Tests for rule_promotion.py — compute_confidence and stage classification."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rule_promotion import compute_confidence
from schemas.production_rule import RuleStage


def test_compute_confidence_raw():
    """Verify base confidence for RAW stage."""
    conf = compute_confidence(RuleStage.RAW, occurrence_count=1,
                              counter_example_count=0, days_since_last_seen=0)
    assert 0.09 <= conf <= 0.11, f"Expected ~0.1 for RAW, got {conf}"


def test_compute_confidence_production():
    """Verify base confidence for PRODUCTION stage."""
    conf = compute_confidence(RuleStage.PRODUCTION, occurrence_count=10,
                              counter_example_count=0, days_since_last_seen=0)
    assert 0.89 <= conf <= 0.91, f"Expected ~0.9 for PRODUCTION, got {conf}"


def test_penalty_from_counter_examples():
    """Verify counter examples reduce confidence."""
    base = compute_confidence(RuleStage.STABLE, occurrence_count=5,
                              counter_example_count=0, days_since_last_seen=0)
    penalized = compute_confidence(RuleStage.STABLE, occurrence_count=5,
                                   counter_example_count=3, days_since_last_seen=0)
    assert penalized < base, f"Expected penalty: {penalized} < {base}"
    assert abs(base - penalized - 0.3) < 0.05, f"Expected penalty ~0.3, got {base - penalized:.3f}"


def test_time_decay():
    """Verify time decay reduces confidence after 30 days."""
    fresh = compute_confidence(RuleStage.STABLE, occurrence_count=5,
                               counter_example_count=0, days_since_last_seen=0)
    old = compute_confidence(RuleStage.STABLE, occurrence_count=5,
                             counter_example_count=0, days_since_last_seen=60)
    assert old < fresh, f"Expected decay: {old} < {fresh}"

    very_old = compute_confidence(RuleStage.STABLE, occurrence_count=5,
                                  counter_example_count=0, days_since_last_seen=90)
    # After 90 days, time_decay = min(1.0, 60/60) = 1.0 → base = 0
    assert very_old < 0.75, f"Expected significant decay at 90d, got {very_old}"


def test_confidence_bounded():
    """Verify confidence is always in [0.0, 1.0]."""
    # Extreme case: RAW with many counter examples and long idle
    conf = compute_confidence(RuleStage.RAW, occurrence_count=0,
                              counter_example_count=20, days_since_last_seen=365)
    assert 0.0 <= conf <= 1.0, f"Expected bounded [0,1], got {conf}"

    # Best case: PRODUCTION with no counters, recent
    conf = compute_confidence(RuleStage.PRODUCTION, occurrence_count=100,
                              counter_example_count=0, days_since_last_seen=0)
    assert 0.0 <= conf <= 1.0, f"Expected bounded [0,1], got {conf}"


def test_stage_values():
    """Verify Stage enum values."""
    assert RuleStage.RAW.value == "raw"
    assert RuleStage.CANDIDATE.value == "candidate"
    assert RuleStage.PRODUCTION.value == "production"


if __name__ == "__main__":
    test_compute_confidence_raw()
    print("PASSED: test_compute_confidence_raw")
    test_compute_confidence_production()
    print("PASSED: test_compute_confidence_production")
    test_penalty_from_counter_examples()
    print("PASSED: test_penalty_from_counter_examples")
    test_time_decay()
    print("PASSED: test_time_decay")
    test_confidence_bounded()
    print("PASSED: test_confidence_bounded")
    test_stage_values()
    print("PASSED: test_stage_values")
