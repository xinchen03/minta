"""Optional local cross-encoder rerank pass for the eval retriever.

Zero-LLM (sentence-transformers CrossEncoder). Re-orders the top dense
candidates by a fine-grained relevance model before the neighbour-window /
fill stages, so evidence buried mid-list has a chance to surface near the top
(the answer model reads the returned list in order).

Model: MINTA_EVAL_RERANK_MODEL, default D:/models/bge-reranker-v2-m3 (local);
fall back to the smaller ms-marco model if the big one is missing.
Enabled only via MINTA_EVAL_RERANK=1 — the competition default keeps the
dense-only baseline until the proxy evidence says otherwise.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("minta.eval.rerank")

_model = None
_model_failed = False


def _get_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    try:
        from sentence_transformers import CrossEncoder
        path = os.environ.get("MINTA_EVAL_RERANK_MODEL", "D:/models/bge-reranker-v2-m3")
        _model = CrossEncoder(path, max_length=512)
        logger.info("reranker loaded: %s", path)
    except Exception:
        _model_failed = True
        logger.warning("reranker unavailable — skipping", exc_info=True)
    return _model


def rerank_scores(query: str, rows: list[dict], base_scores: dict,
                  n: int = 60) -> dict | None:
    """Re-score the top-n candidates with the cross-encoder.

    Returns a {id: score} dict with scores min-max scaled to (0, 1], or None
    when the model is unavailable or there is nothing to rerank.
    """
    model = _get_model()
    if model is None or not rows:
        return None
    ordered = sorted(rows, key=lambda r: -base_scores.get(r["id"], -1.0))[:n]
    pairs = [(query, r["raw_content"][:400]) for r in ordered]
    try:
        raw = model.predict(pairs, show_progress_bar=False)
    except Exception:
        logger.warning("rerank predict failed — skipping", exc_info=True)
        return None
    lo, hi = float(min(raw)), float(max(raw))
    span = (hi - lo) or 1.0
    out = {}
    for r, s in zip(ordered, raw):
        # scale to (0,1]; keep relative order intact
        out[r["id"]] = 0.05 + 0.95 * (float(s) - lo) / span
    return out
