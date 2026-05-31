"""Tests for domain_compiler.py — CPG text → DecisionGraph compilation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.domain_compiler import DomainCompiler

OTTAWA_RULES_TEXT = """
不能负重4步的患者建议拍X光
踝骨后缘压痛的患者建议拍X光
第五跖骨基底压痛的患者建议拍X光
内外踝压痛的患者建议拍X光
以上条件都不满足的患者不需要拍X光
"""


def test_ottawa_rules_flat():
    """Verify Ottawa Ankle Rules compile to exactly 5 rules."""
    compiler = DomainCompiler()
    graph = compiler.compile(OTTAWA_RULES_TEXT, domain="ankle_injury",
                             source="Test Ottawa Rules")
    assert len(graph.nodes) >= 6, f"Expected >=6 nodes (root + 5 rules), got {len(graph.nodes)}"
    assert len(graph.rules) == 5, f"Expected 5 rules, got {len(graph.rules)}"

    # Verify each rule has trigger + action
    for rule in graph.rules:
        assert rule["trigger"], "Rule missing trigger"
        assert rule["action"], "Rule missing action"

    # Check negative rule exists
    negative_rules = [r for r in graph.rules if "不" in r["trigger"] or "不" in r["action"]]
    assert len(negative_rules) >= 1, "Expected at least 1 negative rule"


def test_nested_cpg():
    """Verify nested if-then structures are parsed with correct depth."""
    compiler = DomainCompiler()
    nested_text = """
    如果不能负重4步，建议拍X光。
    如果可以负重但有压痛，建议评估韧带损伤。
    评估韧带损伤时，如果前抽屉试验阳性，建议MRI检查。
    如果前抽屉试验阴性，则保守治疗。
    """
    graph = compiler.compile(nested_text, domain="ankle_injury",
                             source="Test Nested CPG")
    assert len(graph.rules) >= 3, f"Expected >=3 rules, got {len(graph.rules)}"

    depths = [n.metadata.get("nesting_depth", 0) for n in graph.nodes
              if hasattr(n, "metadata") and n.metadata]
    assert any(d > 0 for d in depths), f"Expected nesting (depth > 0), got depths={depths}"


def test_empty_text():
    """Verify empty text returns empty graph."""
    compiler = DomainCompiler()
    graph = compiler.compile("", domain="test")
    assert len(graph.nodes) == 0
    assert len(graph.rules) == 0


def test_english_cpg():
    """Verify English CPG text is parsed."""
    compiler = DomainCompiler()
    english_text = """
    If patient cannot bear weight for 4 steps, recommend radiography.
    If there is malleolar tenderness, recommend radiography.
    If none of the above, no imaging is indicated.
    """
    graph = compiler.compile(english_text, domain="ankle_injury",
                             source="Test English CPG")
    assert len(graph.rules) >= 2, f"Expected >=2 rules, got {len(graph.rules)}"


if __name__ == "__main__":
    test_ottawa_rules_flat()
    print("PASSED: test_ottawa_rules_flat")
    test_nested_cpg()
    print("PASSED: test_nested_cpg")
    test_empty_text()
    print("PASSED: test_empty_text")
    test_english_cpg()
    print("PASSED: test_english_cpg")
