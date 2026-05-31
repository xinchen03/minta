"""Tests for behavior_abstraction.py — surface behavior → cognitive operation mapping."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.behavior_abstraction import BehaviorAbstraction


def test_exact_matches():
    """Verify exact surface form matches."""
    ba = BehaviorAbstraction()
    assert ba.abstract("踝骨后缘压痛") == "PHYSICAL_EXAM_PALPATION"
    assert ba.abstract("不能负重4步") == "WEIGHT_BEARING_TEST"
    assert ba.abstract("建议拍X光") == "IMAGING_REFERRAL"
    assert ba.abstract("不需要拍X光") == "NO_IMAGING_NEEDED"


def test_synonym_normalization():
    """Verify different surface forms map to same abstract operation."""
    ba = BehaviorAbstraction()
    assert ba.abstract("内踝触痛") == "PHYSICAL_EXAM_PALPATION"
    assert ba.abstract("外踝压痛") == "PHYSICAL_EXAM_PALPATION"
    assert ba.abstract("无法承重行走") == "WEIGHT_BEARING_TEST"


def test_english_forms():
    """Verify English surface forms work."""
    ba = BehaviorAbstraction()
    assert ba.abstract("malleolar tenderness") == "PHYSICAL_EXAM_PALPATION"
    assert ba.abstract("unable to walk") == "WEIGHT_BEARING_TEST"


def test_structural_similarity():
    """Verify structural similarity ignores surface wording."""
    ba = BehaviorAbstraction()
    seq_a = ["PHYSICAL_EXAM_PALPATION", "IMAGING_REFERRAL"]
    seq_b = ["踝骨压痛", "拍X光"]
    sim = ba.structural_similarity(seq_a, seq_b)
    assert sim > 0.8, f"Expected similarity > 0.8, got {sim:.3f}"


def test_unknown_form():
    """Verify unknown surface forms return original text."""
    ba = BehaviorAbstraction()
    result = ba.abstract("xyz123_unknown_term")
    assert result == "xyz123_unknown_term"


def test_empty_input():
    """Verify empty input."""
    ba = BehaviorAbstraction()
    assert ba.abstract("") == ""
    assert ba.abstract_sequence([]) == []


if __name__ == "__main__":
    test_exact_matches()
    print("PASSED: test_exact_matches")
    test_synonym_normalization()
    print("PASSED: test_synonym_normalization")
    test_english_forms()
    print("PASSED: test_english_forms")
    test_structural_similarity()
    print("PASSED: test_structural_similarity")
    test_unknown_form()
    print("PASSED: test_unknown_form")
    test_empty_input()
    print("PASSED: test_empty_input")
