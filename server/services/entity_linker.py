"""Entity Linker — lightweight entity extraction via flashtext + regex.

Distilled from Mem0: extracts named entities (persons, projects, tools,
concepts) from context text without spaCy. Uses flashtext for keyword
matching + regex for pattern extraction. Zero model dependency.

Supports entity-based retrieval boosting in multi_signal_retrieval.
"""
from __future__ import annotations
import re
from typing import List, Set, Dict, Optional

# Category patterns (regex, no LLM)
_CATEGORIES = {
    "person": [
        r"\b(?:Dr\.|Mr\.|Ms\.|Mrs\.|Prof\.)\s+[A-Z][a-z]+\b",
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b",  # Full names
        r"@\w+",  # handles/slugs
    ],
    "project": [
        r"\b(?:project|repo|repository)\s+[\"\'](\w+)[\"\']",
        r"\b(?:Minta|BriefBuilder|ChromaDB|FAISS|JEPA|CPG|RRF|BM25|FTS5)\b",
        r"\b(?:the\s+)?(?:system|platform|app|tool)\s+\"(\w+)\"",
    ],
    "tool": [
        r"\b(?:using|with|via|in|on)\s+(\w+(?:\.\w+)?)\s*(?:in|for|to|at|and|,|\.)",
        r"\b(?:Python|FastAPI|React|TypeScript|SQLite|MySQL|Docker|Redis|Git|npm|pip)\b",
        r"\b(?:Claude|GPT|ChatGPT|Copilot|Cursor|Codex)\b",
    ],
    "concept": [
        r"\b(?:algorithm|architecture|pattern|framework|pipeline|workflow|strategy)\b[:\s]*(\w+(?:\s+\w+){0,3})",
        r"\b(?:memory|context|embedding|retrieval|inference|decay|conflict)\s+(?:quality|management|detection|engine)\b",
    ],
    "decision": [
        r"\b(?:decided|chose|selected|picked|went\s+with|opted\s+for)\s+(\w+(?:\s+\w+){0,3})",
        r"\b(?:方案|选择|决定|采用|使用)\s*[：:]\s*(\w+(?:\s+\w+){0,3})",
    ],
}

# Common words to filter out (stop-entities)
_STOP_WORDS = {"the", "a", "an", "this", "that", "it", "is", "was", "are",
               "were", "been", "being", "have", "has", "had", "do", "does",
               "did", "will", "would", "could", "should", "may", "might",
               "can", "shall", "to", "of", "in", "for", "on", "with", "at",
               "by", "from", "as", "into", "through", "during", "before",
               "and", "but", "or", "not", "no", "if", "then", "than", "too"}


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract typed entities from text. Zero LLM, pure regex.

    Returns {category: [entity_name, ...]}.
    """
    if not text:
        return {}

    results: Dict[str, Set[str]] = {}
    for category, patterns in _CATEGORIES.items():
        entities = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entity = match.group(1) if match.lastindex and match.group(1) else match.group(0)
                entity = entity.strip().rstrip(".,;:!?\"'")
                if entity.lower() not in _STOP_WORDS and len(entity) > 1:
                    entities.add(entity)
        if entities:
            results[category] = list(entities)[:5]  # Top 5 per category

    return results


def get_entity_keywords(text: str) -> List[str]:
    """Get all entity names as flat keyword list for search boosting."""
    entities = extract_entities(text)
    all_kw = []
    for cat_entities in entities.values():
        all_kw.extend(cat_entities)
    return list(set(all_kw))  # dedup


def entity_overlap_score(query_entities: List[str], doc_entities: List[str]) -> float:
    """Compute entity overlap score for retrieval boosting.

    Returns score in [0, 1] — higher = more entity overlap.
    """
    if not query_entities or not doc_entities:
        return 0.0
    q_set = set(e.lower() for e in query_entities)
    d_set = set(e.lower() for e in doc_entities)
    overlap = q_set & d_set
    if not overlap:
        return 0.0
    return len(overlap) / max(len(q_set), 1)
