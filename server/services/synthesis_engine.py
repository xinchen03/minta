"""Synthesis Engine — gap-aware context assembly.

Distilled from GBrain: instead of just returning retrieved chunks,
produces a synthesis with:
1. Retrieved context (with source citations)
2. Explicit gap analysis (what the memory store does NOT know)
3. Confidence annotations

Zero LLM cost. Pure structural assembly.
"""
from __future__ import annotations
from typing import List, Dict, Optional


def synthesize_context_pack(
    retrieved: List[Dict],
    query: str,
    total_available: int,
    types_seen: Optional[set] = None,
) -> str:
    """Build a context pack with gap analysis.

    Args:
        retrieved: List of {id, score, summary, body, type, ...} dicts
        query: Original user query
        total_available: Total context objects in store
        types_seen: Set of context types present in retrieved items

    Returns:
        Multi-section context string for injection into LLM prompt.
    """
    sections = []

    # Section 1: Retrieved context
    if retrieved:
        sections.append("## Retrieved Context\n")
        for i, item in enumerate(retrieved[:5]):
            score = item.get("score", item.get("_fused_score", 0))
            summary = item.get("summary", "")[:120]
            ctype = item.get("type", "context")
            sections.append(f"{i+1}. [{ctype}] (relevance: {score:.2f}) {summary}")
        sections.append("")

    # Section 2: Coverage gaps
    gaps = _detect_gaps(retrieved, query, total_available, types_seen)
    if gaps:
        sections.append("## Gaps (information NOT available)\n")
        for gap in gaps:
            sections.append(f"- {gap}")
        sections.append("")

    # Section 3: Quality notes
    notes = _quality_notes(retrieved)
    if notes:
        sections.append("## Quality Notes\n")
        for note in notes:
            sections.append(f"- {note}")
        sections.append("")

    return "\n".join(sections)


def _detect_gaps(
    retrieved: List[Dict],
    query: str,
    total: int,
    types_seen: Optional[set] = None,
) -> List[str]:
    gaps = []

    if not retrieved:
        gaps.append(f"No relevant memories found (searched {total} items).")
        return gaps

    if len(retrieved) < 3:
        gaps.append(f"Only {len(retrieved)} matches found — query may reference information not yet stored.")

    # Low confidence gap
    top_score = retrieved[0].get("score", retrieved[0].get("_fused_score", 0))
    if top_score < 0.3:
        gaps.append(f"Top match has low relevance ({top_score:.2f}) — answer may be unreliable.")

    # Type coverage gap
    if types_seen:
        expected_types = {"preference", "project_context", "decision_criteria", "lesson_learned"}
        missing = expected_types - types_seen
        if missing:
            gaps.append(f"No memories found for: {', '.join(sorted(missing))}.")

    # Staleness gap
    stale_count = sum(1 for r in retrieved if r.get("status") == "stale")
    if stale_count > 0:
        gaps.append(f"{stale_count} of {len(retrieved)} retrieved items are stale — information may be outdated.")

    return gaps


def _quality_notes(retrieved: List[Dict]) -> List[str]:
    notes = []
    if any(r.get("status") == "stale" for r in retrieved):
        notes.append("Some retrieved memories are stale — verify before acting.")
    if len(retrieved) > 0 and all(r.get("score", 0) < 0.5 for r in retrieved):
        notes.append("All matches are low-confidence — consider asking user for clarification.")
    return notes
