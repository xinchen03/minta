"""ComplianceChecker — evaluates resolved profile rules against a manuscript inventory.

Read-only. Never modifies input files. Produces structured + human-readable reports.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manuscript_inventory import ManuscriptInventory
from .rule_evaluator import RuleEvaluator


class ComplianceChecker:
    def __init__(self, profiles_root: Path | None = None):
        if profiles_root is None:
            profiles_root = Path(__file__).resolve().parents[2] / "profiles"
        self._profiles_root = Path(profiles_root)
        self._evaluator = RuleEvaluator()

    def check(
        self,
        profile_id: str,
        source_path: str | Path,
        baseline_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        """Run full compliance check.

        Args:
            profile_id: e.g. 'academic/information-sciences'
            source_path: path to manuscript directory
            baseline_path: optional baseline manifest path

        Returns:
            Structured compliance report dict.
        """
        inventory = ManuscriptInventory(source_path)
        manifest = inventory.build_inventory()

        # Load resolved profile
        from runtime.profile.profile_resolver import ProfileResolver
        resolver = ProfileResolver(self._profiles_root)
        resolved = resolver.resolve(profile_id)

        if not resolved or not resolved.get("rules"):
            return {
                "error": f"Failed to resolve profile '{profile_id}'",
                "resolved": resolved,
            }

        # Detect profile conflicts that would block checking
        conflicts = resolved.get("conflicts", [])
        unresolved_conflicts = [c for c in conflicts if c.get("resolution") != "journal_override"]

        # Evaluate each rule
        checks = []
        summary = {"PASS": 0, "FAIL": 0, "WARNING": 0, "NOT_APPLICABLE": 0, "NOT_CHECKED": 0, "BLOCKED": 0}

        for rule in resolved["rules"]:
            result = self._evaluator.evaluate(rule, manifest)

            # Downgrade if there are unresolved conflicts
            if unresolved_conflicts and result["status"] == "PASS":
                result["status"] = "WARNING"
                result["evaluator_notes"] = (result.get("evaluator_notes", "") +
                    " | Downgraded: unresolved profile conflicts exist")

            checks.append(result)
            status = result["status"]
            if status in summary:
                summary[status] += 1

        report = {
            "profile_id": profile_id,
            "manuscript_baseline": str(baseline_path) if baseline_path else "inventory only",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source_path),
            "summary": summary,
            "rule_count": len(checks),
            "profile_conflicts": conflicts,
            "unresolved_conflicts": len(unresolved_conflicts),
            "checks": checks,
            "manuscript_metadata": manifest.get("manuscript_metadata", {}),
            "components": manifest.get("components", {}),
        }

        return report

    def render_markdown(self, report: Dict[str, Any]) -> str:
        """Render a user-readable markdown compliance report."""
        summary = report.get("summary", {})
        checks = report.get("checks", [])
        meta = report.get("manuscript_metadata", {})

        lines = [
            f"# Information Sciences — 投稿合规报告",
            f"",
            f"**生成时间**: {report.get('generated_at', '')[:19]}",
            f"**Profile**: {report.get('profile_id', '')}",
            f"**稿件路径**: {report.get('source_path', '')}",
            f"",
            f"## 概要",
            f"",
            f"| 状态 | 数量 |",
            f"|------|------|",
            f"| ✅ PASS | {summary.get('PASS', 0)} |",
            f"| ❌ FAIL | {summary.get('FAIL', 0)} |",
            f"| ⚠️ WARNING | {summary.get('WARNING', 0)} |",
            f"| ➖ NOT_APPLICABLE | {summary.get('NOT_APPLICABLE', 0)} |",
            f"| ❓ NOT_CHECKED | {summary.get('NOT_CHECKED', 0)} |",
            f"| 🚫 BLOCKED | {summary.get('BLOCKED', 0)} |",
            f"",
        ]

        # Failures first
        fails = [c for c in checks if c["status"] == "FAIL"]
        if fails:
            lines.append("## 投稿阻塞项 (FAIL)")
            lines.append("")
            for c in fails:
                lines.append(f"### {c['rule_id']}: {c.get('requirement', '')[:100]}")
                lines.append(f"")
                lines.append(f"**要求**: {c.get('required_value', 'N/A')}")
                lines.append(f"**实际**: {json.dumps(c.get('observed', {}), ensure_ascii=False)}")
                if c.get("recommended_action"):
                    lines.append(f"**建议**: {c['recommended_action']}")
                lines.append("")

        # Warnings
        warns = [c for c in checks if c["status"] == "WARNING"]
        if warns:
            lines.append("## 重要风险 (WARNING)")
            lines.append("")
            for c in warns:
                lines.append(f"- **{c['rule_id']}**: {c.get('requirement', '')[:120]}")
                if c.get("evaluator_notes"):
                    lines.append(f"  - *{c['evaluator_notes']}*")
            lines.append("")

        # NOT_CHECKED
        not_checked = [c for c in checks if c["status"] == "NOT_CHECKED"]
        if not_checked:
            lines.append("## 尚无法验证")
            lines.append("")
            for c in not_checked:
                lines.append(f"- **{c['rule_id']}** [{c.get('strength', '')}]: {c.get('requirement', '')[:120]}")
            lines.append("")

        # PASS (summary only)
        passed = [c for c in checks if c["status"] == "PASS"]
        if passed:
            lines.append(f"## 已通过 ({len(passed)} 项)")
            lines.append("")
            lines.append("| 规则 | 类别 | 要求 |")
            lines.append("|------|------|------|")
            for c in passed[:20]:
                req = c.get('requirement', '')[:80]
                lines.append(f"| {c['rule_id']} | {c.get('category', '')} | {req} |")
            if len(passed) > 20:
                lines.append(f"| ... | | *等 {len(passed) - 20} 项* |")
            lines.append("")

        return "\n".join(lines)
