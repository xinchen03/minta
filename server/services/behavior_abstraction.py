"""Behavior Abstraction Layer — map surface behaviors to domain-independent cognitive operations.

Based on:
- Clinical reasoning literature (Elstein 1978, Schmidt 1990)
- Cognitive Task Analysis (Crandall 2006)
- ACT-R base-level productions (Anderson 2004)
- Structure-Mapping Theory (Gentner 1983)
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from difflib import SequenceMatcher

ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "ontology" / "behavior_ontology.json"


class BehaviorAbstraction:
    """Map surface clinical behaviors to abstract cognitive operations.

    >>> ba = BehaviorAbstraction()
    >>> ba.abstract("踝骨后缘压痛")
    'PHYSICAL_EXAM_PALPATION'
    >>> ba.abstract("内踝触痛")
    'PHYSICAL_EXAM_PALPATION'
    >>> ba.abstract("不能负重4步")
    'WEIGHT_BEARING_TEST'
    >>> ba.abstract("建议拍X光")
    'IMAGING_REFERRAL'
    """

    def __init__(self, ontology_path: Optional[str] = None):
        path = Path(ontology_path) if ontology_path else ONTOLOGY_PATH
        with open(path, "r", encoding="utf-8") as f:
            self.ontology = json.load(f)
        self.operations = self.ontology.get("operations", {})
        self._build_index()

    def _build_index(self) -> None:
        """Build reverse index: surface_form → operation_name."""
        self._surface_index: Dict[str, str] = {}
        self._surface_lower: Dict[str, str] = {}
        for op_name, op_data in self.operations.items():
            for form in op_data.get("surface_forms", []):
                self._surface_index[form] = op_name
                self._surface_lower[form.lower()] = op_name

    def abstract(self, surface_behavior: str) -> str:
        """Map a surface behavior string to its abstract cognitive operation.

        Returns the operation name (e.g. 'PHYSICAL_EXAM_PALPATION')
        or the original string if no mapping found.
        """
        if not surface_behavior:
            return ""

        # 1. Exact match
        if surface_behavior in self._surface_index:
            return self._surface_index[surface_behavior]

        # 2. Case-insensitive match
        lower = surface_behavior.lower()
        if lower in self._surface_lower:
            return self._surface_lower[lower]

        # 3. Fuzzy substring match (relaxed: form contained in text → strong signal)
        best_op = None
        best_score = 0.0
        best_len = 0
        for form, op_name in self._surface_lower.items():
            if form in lower:
                score = len(form) / max(len(lower), len(form))
                # Boost: form >= 15 chars embedded in longer text → likely a key phrase match
                if len(form) >= 15:
                    score = max(score, 0.55)
                if score > best_score or (score == best_score and len(form) > best_len):
                    best_score = score
                    best_len = len(form)
                    best_op = op_name
            elif lower in form:
                score = len(lower) / len(form)
                if score > best_score:
                    best_score = score
                    best_len = len(lower)
                    best_op = op_name

        if best_op and best_score >= 0.25:
            return best_op

        # 3.5 Token-window match: check if surface form tokens appear
        # consecutively within the long clinical text (handles embedded phrases)
        if best_op is None:
            text_tokens = lower.replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
            best_tok_score = 0.0
            best_tok_op = None
            for form, op_name in self._surface_lower.items():
                form_tokens = form.replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
                if len(form_tokens) < 2:
                    continue
                # Sliding window: check if form tokens appear in sequence
                for i in range(len(text_tokens) - len(form_tokens) + 1):
                    window = text_tokens[i:i + len(form_tokens)]
                    match_count = sum(1 for f, w in zip(form_tokens, window) if f == w or f in w or w in f)
                    score = match_count / len(form_tokens)
                    if score > best_tok_score:
                        best_tok_score = score
                        best_tok_op = op_name
            if best_tok_op and best_tok_score >= 0.6:
                return best_tok_op

        # 4. Chinese character n-gram overlap (for Chinese medical terminology)
        if re.search(r'[一-鿿]', surface_behavior):
            best_op = self._chinese_overlap_match(lower)
            if best_op:
                return best_op

        return surface_behavior

    def _chinese_overlap_match(self, text_lower: str) -> Optional[str]:
        """Match Chinese text by character bigram overlap with surface forms."""
        text_bigrams = set(text_lower[i:i+2] for i in range(len(text_lower) - 1))
        if not text_bigrams:
            return None

        best_op = None
        best_jaccard = 0.0
        for form_lower, op_name in self._surface_lower.items():
            form_bigrams = set(form_lower[i:i+2] for i in range(len(form_lower) - 1))
            if not form_bigrams:
                continue
            intersection = text_bigrams & form_bigrams
            union = text_bigrams | form_bigrams
            jaccard = len(intersection) / len(union) if union else 0
            if jaccard > best_jaccard and jaccard >= 0.3:
                best_jaccard = jaccard
                best_op = op_name

        return best_op

    def abstract_sequence(self, behaviors: List[str]) -> List[str]:
        """Map a sequence of surface behaviors to abstract operation sequence."""
        return [self.abstract(b) for b in behaviors]

    def structural_similarity(self, seq_a: List[str], seq_b: List[str]) -> float:
        """Compare two abstract operation sequences for structural similarity.

        Uses abstract operations, NOT surface strings. Two sequences
        describing the same clinical reasoning pattern should score high
        even if they use different surface terminology.

        >>> ba = BehaviorAbstraction()
        >>> seq_a = ["PHYSICAL_EXAM_PALPATION", "IMAGING_REFERRAL"]
        >>> seq_b = ["踝骨压痛", "拍X光"]
        >>> ba.structural_similarity(seq_a, seq_b) > 0.85
        True
        """
        # Normalize both sequences to abstract operations
        ops_a = [self.abstract(s) if s in self._surface_index else s for s in seq_a]
        ops_b = [self.abstract(s) for s in seq_b]

        # SequenceMatcher on the operation sequences
        sm = SequenceMatcher(None, ops_a, ops_b)
        return sm.ratio()

    def get_operation_info(self, operation_name: str) -> dict:
        """Get metadata about an operation."""
        return self.operations.get(operation_name, {})

    def list_operations_by_category(self, category: str) -> List[str]:
        """List all operation names in a given category."""
        return [
            name for name, data in self.operations.items()
            if data.get("category") == category
        ]

    def add_surface_form(self, operation_name: str, surface_form: str) -> bool:
        """Dynamically add a new surface form to an existing operation.
        Returns True if added, False if operation doesn't exist or form duplicates.
        """
        if operation_name not in self.operations:
            return False
        forms = self.operations[operation_name].setdefault("surface_forms", [])
        if surface_form in forms:
            return False
        forms.append(surface_form)
        self._build_index()
        return True
