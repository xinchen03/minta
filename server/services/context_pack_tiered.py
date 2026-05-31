"""Tiered Context Pack builder — L0/L1/L2 progressive loading.

L0: One-line summaries (~20 tokens each) → LLM scans first
L1: Key fields (~200 tokens each) → expand interesting ones
L2: Full content (no truncation) → expand rarely

Token budget is dynamic, configurable per scene.
Based on OpenViking's three-tier loading approach (saves 40-60% tokens).
"""
from __future__ import annotations
import logging
import json
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = 1500
L0_CHARS_PER_ITEM = 80    # ~20 tokens
L1_CHARS_PER_ITEM = 800   # ~200 tokens
L2_CHARS_PER_ITEM = 5000  # unlimited in practice


class TieredContextPackBuilder:
    """Build context packs with progressive disclosure (L0/L1/L2)."""

    def __init__(self, token_budget: int = DEFAULT_BUDGET):
        self.token_budget = token_budget
        self.char_budget = token_budget * 4  # rough: 1 token ≈ 4 chars

    def build(
        self,
        context_objects: List[dict],
        query: str = "",
        scene: str = "general",
    ) -> dict:
        """Build a tiered context pack from context objects.

        Returns dict with keys: l0, l1, l2, flat (for legacy consumers).
        """
        if not context_objects:
            return {"l0": [], "l1": [], "l2": [], "flat": ""}

        # Sort by relevance (use _fused_score if available, else confidence)
        scored = sorted(
            context_objects,
            key=lambda o: (
                o.get("_fused_score", 0) * 100
                + (o.get("confidence", 0) / 5.0)
            ),
            reverse=True,
        )

        # Allocate budget across tiers
        l0_budget = max(1, int(len(scored) * 0.5))
        l1_budget = max(1, int(len(scored) * 0.3))
        l2_budget = max(1, int(len(scored) * 0.1))

        l0_items = self._build_l0(scored[:l0_budget])
        l1_items = self._build_l1(scored[:l1_budget])
        l2_items = self._build_l2(scored[:l2_budget])

        flat = self._build_flat(l0_items, l1_items, l2_items)

        return {
            "l0": l0_items,
            "l1": l1_items,
            "l2": l2_items,
            "flat": flat,
        }

    def _build_l0(self, objects: List[dict]) -> List[dict]:
        """L0: one-line summaries — just enough for LLM to know what's available."""
        items = []
        for obj in objects:
            summary = (obj.get("summary") or obj.get("title", ""))[:L0_CHARS_PER_ITEM]
            if summary:
                items.append({
                    "id": obj.get("id", ""),
                    "type": obj.get("type", ""),
                    "title": obj.get("title", ""),
                    "summary": summary,
                })
        return items

    def _build_l1(self, objects: List[dict]) -> List[dict]:
        """L1: key fields — title, full summary, tags, confidence."""
        items = []
        for obj in objects:
            body = (obj.get("body") or "")[:L1_CHARS_PER_ITEM]
            items.append({
                "id": obj.get("id", ""),
                "type": obj.get("type", ""),
                "title": obj.get("title", ""),
                "summary": obj.get("summary", ""),
                "body_preview": body,
                "tags": obj.get("tags", []),
                "confidence": obj.get("confidence", 0),
                "source": obj.get("source", ""),
            })
        return items

    def _build_l2(self, objects: List[dict]) -> List[dict]:
        """L2: full content — no truncation."""
        return [
            {
                "id": obj.get("id", ""),
                "type": obj.get("type", ""),
                "title": obj.get("title", ""),
                "summary": obj.get("summary", ""),
                "body": obj.get("body", ""),
                "tags": obj.get("tags", []),
                "confidence": obj.get("confidence", 0),
                "source": obj.get("source", ""),
                "status": obj.get("status", ""),
            }
            for obj in objects
        ]

    def _build_flat(
        self,
        l0: List[dict],
        l1: List[dict],
        l2: List[dict],
    ) -> str:
        """Build a flat text representation suitable for LLM context injection."""
        seen_ids = set()
        lines = []

        def add_section(heading: str, items: List[dict], max_chars: Optional[int] = None):
            nonlocal lines
            section_lines = [heading]
            used = 0
            for item in items:
                if item["id"] in seen_ids:
                    continue
                seen_ids.add(item["id"])
                entry = f"- [{item.get('type', '?')}] {item.get('title', '')}"
                if item.get("summary"):
                    entry += f": {item['summary'][:120]}"
                if max_chars and used + len(entry) > max_chars:
                    break
                section_lines.append(entry)
                used += len(entry)
            lines.extend(section_lines[:50])

        add_section("## Expert Rules (L1)", l1, 600)
        add_section("## Context (L0)", l0, 400)

        return "\n".join(lines)
