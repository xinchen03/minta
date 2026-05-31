"""Context Pack builder — compose pinned slots into injectable context.

Scene-aware: different slot order/emphasis per use case.
Token budget: max ~3500 chars for safe injection.

V2: Integrated with synthesis_engine for gap analysis.
"""
from __future__ import annotations
import logging
from typing import List, Tuple, Dict, Optional

from services.synthesis_engine import synthesize_context_pack

logger = logging.getLogger(__name__)

MAX_PACK_CHARS = 3500
THETA_R = 0.85

SCENE_ORDERS = {
    "coding": ["persona", "preferences", "rules", "knowledge", "counter_examples", "skills", "pending"],
    "writing": ["persona", "preferences", "rules", "knowledge", "skills", "counter_examples", "pending"],
    "research": ["persona", "knowledge", "preferences", "rules", "skills", "counter_examples", "pending"],
    "general": ["persona", "preferences", "rules", "knowledge", "counter_examples", "skills", "pending"],
    "auto": ["persona", "preferences", "rules", "knowledge", "counter_examples", "skills", "pending"],
}


def build_context_pack(slots: list, scene: str = "auto", expert_directory: list = None) -> str:
    """Build a Context Pack string from slot objects.

    If expert_directory is provided, a lightweight domain listing is injected
    (~80 tokens) so the AI knows which experts are available and can query
    specific rules on-demand via the Minta API.
    """
    if not slots:
        return ""

    order = SCENE_ORDERS.get(scene, SCENE_ORDERS["auto"])
    slot_map = {s.label: s.content for s in slots}

    sections: List[Tuple[str, str]] = []

    for label in order:
        content = slot_map.get(label, "").strip()
        if not content:
            continue

        headings = {
            "persona": "## Your Profile",
            "preferences": "## Your Preferences",
            "knowledge": "## Project Context",
            "counter_examples": "## Recent Lessons",
            "skills": "## Active Skills",
            "pending": "## Pending Items",
            "rules": "## Active Rules & Guidelines",
        }
        heading = headings.get(label, f"## {label}")
        sections.append((heading, content))

    if not sections and not expert_directory:
        return ""

    # ── Minta Expert: lightweight directory (~80 tokens) ──
    if expert_directory:
        dir_lines = []
        for d in expert_directory:
            domain = d.get("domain", "?")
            count = d.get("rule_count", 0)
            sources = d.get("sources", [])
            src_str = sources[0][:60] if sources else "CPG compiled"
            dir_lines.append(f"- {domain}: {count} rules ({src_str})")
        domain_list = ", ".join(d["domain"] for d in expert_directory)

        if dir_lines:
            # Lightweight directory
            sections.insert(0, (
                "## Minta Expert — Available Domains",
                "\n".join(dir_lines) + "\n\n"
                f"When the conversation involves any of [{domain_list}], "
                f"use expert rules. Query rules via the Minta API: "
                f"GET /api/expert/productions?domain=X."
            ))

    # Build with budget
    header = "# Minta Context\n"
    budget = MAX_PACK_CHARS - len(header)
    lines = [header]
    used = 0

    for heading, content in sections:
        block = f"\n{heading}\n{content}\n"
        if used + len(block) <= budget:
            lines.append(block)
            used += len(block)
        else:
            remaining = budget - used - len(heading) - 4
            if remaining > 80:
                truncated = content[:remaining] + "\n..."
                lines.append(f"\n{heading}\n{truncated}\n")
            break

    return "".join(lines)


def build_context_pack_v2(
    slots: list,
    scene: str = "auto",
    expert_directory: list = None,
    retrieved_contexts: List[Dict] = None,
    query: str = "",
    total_objects: int = 0,
) -> str:
    """Build Context Pack V2 — with gap analysis (distilled from GBrain)."""
    pack = build_context_pack(slots, scene, expert_directory)
    if not retrieved_contexts:
        return pack

    types_seen = {r.get("type", "") for r in retrieved_contexts if r.get("type")}
    gap_section = synthesize_context_pack(
        retrieved=retrieved_contexts,
        query=query,
        total_available=total_objects,
        types_seen=types_seen,
    )

    gap_lines = gap_section.split("\n")
    gap_short = "\n".join(gap_lines[:8])
    if len(pack) + len(gap_short) > MAX_PACK_CHARS:
        gap_short = "\n".join(gap_lines[:4])
    if len(pack) + len(gap_short) <= MAX_PACK_CHARS:
        return pack + "\n\n" + gap_short
    return pack


# ── Embedding-based clustering + greedy knapsack ──

def cluster_entries(
    entries: List[Dict],
    embeddings: Optional[Dict[str, list]] = None,
    theta_r: float = THETA_R,
) -> List[List[Dict]]:
    """Cluster context entries by cosine similarity (single-linkage).

    Args:
        entries: List of dicts with 'id', 'text', optional 'retention'.
        embeddings: Optional dict mapping entry id → embedding vector.
        theta_r: Cosine similarity threshold for merging.

    Returns:
        List of clusters, each a list of entries.
    """
    import numpy as np

    n = len(entries)
    if n <= 1:
        return [[e] for e in entries]

    # Compute pairwise cosine similarity
    sim_matrix = {}
    for i in range(n):
        for j in range(i + 1, n):
            if embeddings:
                ei = np.array(embeddings.get(entries[i]["id"], []), dtype=float)
                ej = np.array(embeddings.get(entries[j]["id"], []), dtype=float)
                if len(ei) == 0 or len(ej) == 0:
                    sim = 0.0
                else:
                    sim = float(np.dot(ei, ej) / (np.linalg.norm(ei) * np.linalg.norm(ej)))
            else:
                # Fallback: text overlap similarity (Jaccard on word sets)
                ti = set(entries[i].get("text", "").lower().split())
                tj = set(entries[j].get("text", "").lower().split())
                sim = len(ti & tj) / max(len(ti | tj), 1)
            sim_matrix[(i, j)] = sim

    # Union-find clustering
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for (i, j), sim in sim_matrix.items():
        if sim > theta_r:
            union(i, j)

    clusters: Dict[int, List[Dict]] = {}
    for i, entry in enumerate(entries):
        root = find(i)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(entry)

    return list(clusters.values())


def pack_knapsack(
    clusters: List[List[Dict]],
    budget_chars: int,
) -> str:
    """Greedy knapsack: select one representative per cluster, order by topic then recency.

    Each cluster contributes its highest-retention entry. Entries are packed
    in topic-coherence order until the character budget is exhausted.

    Args:
        clusters: List of entry clusters.
        budget_chars: Maximum total characters for the packed brief.

    Returns:
        Packed text string.
    """
    # Select representative per cluster (highest retention or first)
    reps = []
    for cluster in clusters:
        if not cluster:
            continue
        # Pick entry with highest retention, or first if no retention field
        best = max(cluster, key=lambda e: e.get("retention", 0.5))
        reps.append(best)

    # Sort by topic (type) then recency
    reps.sort(key=lambda e: (
        e.get("type", ""),
        -(e.get("created_ts", 0)),
    ))

    # Greedy pack
    lines = []
    used = 0
    for entry in reps:
        text = entry.get("text", f"{entry.get('title', '')}: {entry.get('summary', '')}")
        block = f"- {text}\n"
        if used + len(block) <= budget_chars:
            lines.append(block)
            used += len(block)
        elif used < budget_chars * 0.8:
            # Try truncated version for last entry
            remaining = budget_chars - used - 5
            if remaining > 40:
                lines.append(f"- {text[:remaining]}...\n")
            break
        else:
            break

    return "".join(lines)


def build_context_pack_from_objects(
    objects: List[Dict],
    budget_chars: int = 2000,
    embeddings: Optional[Dict[str, list]] = None,
) -> str:
    """Build a token-budgeted brief from context objects.

    Clusters by embedding similarity, selects representatives,
    and packs greedily under the budget.

    Args:
        objects: List of dicts with id, title, summary, text, type, retention, etc.
        budget_chars: Character budget.
        embeddings: Optional id → embedding vector mapping.

    Returns:
        Packed brief string.
    """
    if not objects:
        return ""

    entries = []
    for obj in objects:
        entries.append({
            "id": obj.get("id", ""),
            "title": obj.get("title", ""),
            "summary": obj.get("summary", ""),
            "text": obj.get("text", obj.get("summary", f"{obj.get('title', '')}")),
            "type": obj.get("type", ""),
            "retention": obj.get("retention", 0.5),
            "created_ts": obj.get("created_ts", 0),
        })

    clusters = cluster_entries(entries, embeddings)
    return pack_knapsack(clusters, budget_chars)
