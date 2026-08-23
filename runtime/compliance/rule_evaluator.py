"""RuleEvaluator — evaluates a single profile rule against manuscript inventory.

Each rule has an evaluation_mode that determines how it's checked:
- automated: programmatic check
- semi-automated: programmatic signal + needs human review
- manual-review: always NOT_CHECKED, requires human judgment
- deferred: cannot check from local files (e.g., submission system fields)
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


class RuleEvaluator:
    def evaluate(self, rule: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single rule against a manuscript inventory.

        Returns a check dict with status, observed, evidence, recommended_action.
        Never modifies input files.
        """
        rule_id = rule.get("rule_id", "")
        category = rule.get("category", "")
        evaluation_mode = rule.get("evaluation_mode", self._infer_mode(rule))
        requirement = rule.get("requirement", "")
        strength = rule.get("strength", "academic-common")

        base = {
            "rule_id": rule_id,
            "status": "NOT_CHECKED",
            "category": category,
            "strength": strength,
            "evaluation_mode": evaluation_mode,
            "requirement": requirement,
            "observed": {},
            "required_value": "",
            "evidence": {},
            "recommended_action": None,
            "evaluator_notes": None,
        }

        # Deferred/manual: cannot auto-check
        if evaluation_mode in ("manual-review", "deferred"):
            base["evaluator_notes"] = f"Cannot auto-check ({evaluation_mode})"
            return base

        # Route to specific checkers by category + rule_id pattern
        if category == "abstract":
            return self._check_abstract(rule_id, manifest, base)
        elif category == "keywords":
            return self._check_keywords(manifest, base)
        elif category == "highlights":
            return self._check_highlights(manifest, base)
        elif category == "section_numbering":
            return self._check_not_applicable(base, "Section numbering check requires full .tex parse")
        elif category == "acknowledgements":
            return self._check_acknowledgements(manifest, base)
        elif category == "conclusions":
            return self._check_conclusions(manifest, base)
        elif category == "length":
            return self._check_not_applicable(base, "Page count from .tex is approximate")
        elif category == "title_page":
            return self._check_title_page(manifest, base)
        elif category == "author_contributions":
            return self._check_not_checked(base, "CRediT statement needs manual review")
        elif category == "vitae":
            return self._check_not_checked(base, "Author bios not verifiable from manuscript")
        elif category == "appendices":
            return self._check_appendices(manifest, base)
        elif category == "file_format":
            return self._check_file_format(manifest, base)
        elif category == "figures":
            return self._check_figures(manifest, base)
        elif category == "tables":
            return self._check_tables(manifest, base)
        elif category == "math":
            return self._check_not_checked(base, "Math formatting requires .tex source parse")
        elif category == "references":
            return self._check_references(manifest, base)
        elif category == "scope_fit":
            return self._check_not_checked(base, "Scope fit requires human/LLM review")
        elif category == "editorial_risk":
            return self._check_not_checked(base, "Editorial risk assessment requires human/LLM review")
        elif category == "submission":
            return self._check_submission(manifest, base)
        elif category == "ethics":
            return self._check_not_checked(base, "Ethics declarations require manual verification")
        elif category == "funding":
            return self._check_not_checked(base, "Funding statement requires manual check")
        elif category == "research_data":
            return self._check_not_checked(base, "Data availability statement requires manual check")
        elif category == "proof":
            return self._check_not_applicable(base, "Proof stage — not applicable at submission")
        elif category == "anonymity":
            return self._check_not_checked(base, "Review process rule — not verifiable from manuscript")
        elif category == "claim_strength":
            return self._check_not_checked(base, "Claim strength requires human/LLM review")
        else:
            base["evaluator_notes"] = f"No evaluator for category '{category}'"
            return base

    # ── Specific checkers ──

    def _check_abstract(self, rule_id: str, manifest: Dict, base: Dict) -> Dict:
        meta = manifest.get("manuscript_metadata", {})
        wc = meta.get("abstract_word_count")

        if wc is None:
            base["evaluator_notes"] = "Could not extract abstract from .tex files"
            return base

        base["observed"] = {"abstract_word_count": wc}

        if rule_id == "INS-ABS-001":
            base["required_value"] = "Maximum 250 words"
            base["evidence"] = {"source": "abstract environment in .tex files"}
            if wc <= 250:
                base["status"] = "PASS"
            else:
                base["status"] = "FAIL"
                base["recommended_action"] = f"Reduce abstract by {wc - 250} words (currently {wc})"

        elif rule_id == "INS-ABS-002":
            base["status"] = "NOT_CHECKED"
            base["evaluator_notes"] = "Abstract self-containedness requires human review"

        return base

    def _check_keywords(self, manifest: Dict, base: Dict) -> Dict:
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = "Keyword count and format require .tex parse"
        return base

    def _check_highlights(self, manifest: Dict, base: Dict) -> Dict:
        # Check if highlights file exists
        files = manifest.get("files", [])
        has_highlights = any("highlight" in f["path"].lower() for f in files)
        base["observed"] = {"highlights_file_found": has_highlights}
        if has_highlights:
            base["status"] = "PASS"
            base["evaluator_notes"] = "Highlights file found; content check deferred"
        else:
            base["status"] = "NOT_CHECKED"
            base["evaluator_notes"] = "Highlights recommended but not mandatory; file not found"
        return base

    def _check_acknowledgements(self, manifest: Dict, base: Dict) -> Dict:
        meta = manifest.get("manuscript_metadata", {})
        base["observed"] = {"has_acknowledgements_section": meta.get("has_acknowledgements", False)}
        base["status"] = "PASS" if meta.get("has_acknowledgements") else "NOT_CHECKED"
        return base

    def _check_conclusions(self, manifest: Dict, base: Dict) -> Dict:
        meta = manifest.get("manuscript_metadata", {})
        base["observed"] = {"has_conclusions_section": meta.get("has_conclusions", False)}
        if meta.get("has_conclusions"):
            base["status"] = "PASS"
        else:
            base["status"] = "FAIL"
            base["recommended_action"] = "Add a Conclusions section as required by the journal"
        return base

    def _check_title_page(self, manifest: Dict, base: Dict) -> Dict:
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = "Title page completeness requires human review of author details"
        return base

    def _check_appendices(self, manifest: Dict, base: Dict) -> Dict:
        meta = manifest.get("manuscript_metadata", {})
        base["observed"] = {"has_appendix": meta.get("has_appendix", False)}
        base["status"] = "PASS" if meta.get("has_appendix") else "NOT_APPLICABLE"
        if not meta.get("has_appendix"):
            base["evaluator_notes"] = "No appendices detected; rule applies only if appendices exist"
        return base

    def _check_file_format(self, manifest: Dict, base: Dict) -> Dict:
        files = manifest.get("files", [])
        tex_files = [f for f in files if f["path"].endswith(".tex")]
        has_pdf_only = all(f["path"].endswith(".pdf") for f in files)
        base["observed"] = {"tex_files": len(tex_files), "total_files": len(files)}
        if has_pdf_only:
            base["status"] = "FAIL"
            base["recommended_action"] = "PDF is not acceptable. Submit .tex or .doc/.docx source files."
        elif tex_files:
            base["status"] = "PASS"
            base["evidence"] = {"tex_files": [f["path"] for f in tex_files[:5]]}
        else:
            base["status"] = "NOT_CHECKED"
        return base

    def _check_figures(self, manifest: Dict, base: Dict) -> Dict:
        figs = manifest.get("components", {}).get("figure_files", 0)
        base["observed"] = {"figure_count": figs}
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = f"{figs} figure files detected; resolution and format check deferred"
        return base

    def _check_tables(self, manifest: Dict, base: Dict) -> Dict:
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = "Table format (editable text) requires .tex source inspection"
        return base

    def _check_references(self, manifest: Dict, base: Dict) -> Dict:
        files = manifest.get("files", [])
        has_bib = any(f["path"].endswith(".bib") for f in files)
        base["observed"] = {"has_bib_file": has_bib}
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = "Reference consistency check requires .tex + .bib cross-reference"
        return base

    def _check_submission(self, manifest: Dict, base: Dict) -> Dict:
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = "Submission system fields (author list, declarations) not verifiable locally"
        return base

    # ── Helpers ──

    def _check_not_applicable(self, base: Dict, note: str) -> Dict:
        base["status"] = "NOT_APPLICABLE"
        base["evaluator_notes"] = note
        return base

    def _check_not_checked(self, base: Dict, note: str) -> Dict:
        base["status"] = "NOT_CHECKED"
        base["evaluator_notes"] = note
        return base

    @staticmethod
    def _infer_mode(rule: Dict) -> str:
        """Infer evaluation_mode from category if not explicitly set."""
        cat = rule.get("category", "")
        manual_cats = {"editorial_risk", "scope_fit", "claim_strength", "anonymity", "ethics", "funding", "research_data"}
        deferred_cats = {"submission"}
        if cat in manual_cats:
            return "manual-review"
        if cat in deferred_cats:
            return "deferred"
        return "semi-automated"
