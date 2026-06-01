"""Cross-Encoder Reranker — coarse-to-fine retrieval.

Distilled from MemPal: ChromaDB does coarse retrieval (top-20),
Cross-Encoder does fine ranking (→ top-5).

Default: ms-marco-MiniLM-L-6-v2 (~80MB, English, fast).
Override: MINTA_RERANKER_MODEL env var for BAAI/bge-reranker-v2-m3 (CN+EN, 568MB).
Zero LLM cost. ~50ms per pair on CPU.
"""
from __future__ import annotations
import os
import logging
from typing import List, Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

_RERANKER = None  # lazy load

_RERANKER_MODEL = os.environ.get(
    "MINTA_RERANKER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)


def _get_reranker():
    global _RERANKER
    if _RERANKER is None:
        try:
            from sentence_transformers import CrossEncoder
            _RERANKER = CrossEncoder(_RERANKER_MODEL, max_length=512)
            logger.info(f"Reranker: loaded {_RERANKER_MODEL}")
        except Exception as e:
            logger.warning(f"Reranker unavailable: {e}")
            _RERANKER = False
    return _RERANKER if _RERANKER is not False else None


def rerank(
    query: str,
    candidates: List[Dict],
    top_k: int = 5,
    threshold: float = 0.0,
) -> List[Dict]:
    """Re-rank candidates using Cross-Encoder.

    Args:
        query: Search query
        candidates: List of {id, score, summary, body, ...} from coarse retrieval
        top_k: Number of results to return after reranking
        threshold: Minimum relevance score (0-1)

    Returns:
        Re-ranked list, each with _rerank_score added.
    """
    model = _get_reranker()
    if model is False or not candidates:
        return candidates[:top_k]

    pairs = []
    for c in candidates[:20]:  # max 20 candidates to rerank
        text = f"{c.get('summary', '')} {c.get('body', '')}"[:400]
        pairs.append((query, text))

    try:
        scores = model.predict(pairs, show_progress_bar=False)
    except Exception as e:
        logger.warning(f"Rerank failed: {e}")
        return candidates[:top_k]

    # Attach rerank scores and sort
    for i, c in enumerate(candidates[:len(scores)]):
        c["_rerank_score"] = round(float(scores[i]), 4)

    reranked = sorted(
        [c for c in candidates if c.get("_rerank_score", 0) >= threshold],
        key=lambda x: x.get("_rerank_score", 0),
        reverse=True,
    )
    return reranked[:top_k]


def is_available() -> bool:
    return _get_reranker() is not None
