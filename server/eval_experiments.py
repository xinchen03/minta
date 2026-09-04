"""Env-gated experiment arms for the eval retriever. ALL arms default OFF.

v3 discipline: the competition configuration is fidelity-first + context-first
+ evidence-backed governance. Nothing here is enabled without an env flag, and
an arm only earns its place through the local end-to-end proxy score — not
because Minta the product ships governance machinery.

Switches (env):
    MINTA_EVAL_RADIUS          neighbour window radius          default 1
    MINTA_EVAL_ENVELOPE        role/timestamp envelope          default on
    MINTA_EVAL_BM25            lexical BM25 channel             default 0
    MINTA_EVAL_RECALL_QUERY    gpt-4o-mini first-person recall  default 0
    MINTA_EVAL_RECALL_WEIGHT   fusion weight of recall query    default 0.5
    MINTA_EVAL_LLM_BASE/KEY/MODEL  (MODEL default gpt-4o-mini)  empty = LLM off

The embed function is injected by eval_app once the (lazy, local) embedder is
available; until then every vector arm degrades to None and the retriever uses
its offline recency fallback — the endpoint stays fully contract-compliant.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("minta.eval.experiments")

_EMBED_FN = None  # injected by eval_app / eval_embed


def set_embed_fn(fn) -> None:
    global _EMBED_FN
    _EMBED_FN = fn


def experiments() -> "Experiments":
    return Experiments()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Experiments:
    """Reads env on construction; cheap enough to build per search."""

    def window_radius(self) -> int:
        return max(0, _env_int("MINTA_EVAL_RADIUS", 1))

    def envelope_enabled(self) -> bool:
        return os.environ.get("MINTA_EVAL_ENVELOPE", "on").lower() != "off"

    def bm25_enabled(self) -> bool:
        return os.environ.get("MINTA_EVAL_BM25", "0").lower() in ("1", "true", "on")

    def recall_query_enabled(self) -> bool:
        return os.environ.get("MINTA_EVAL_RECALL_QUERY", "0").lower() in ("1", "true", "on") \
            and self._llm_ready()

    def recall_weight(self) -> float:
        try:
            return float(os.environ.get("MINTA_EVAL_RECALL_WEIGHT", "0.5"))
        except ValueError:
            return 0.5

    @staticmethod
    def _llm_ready() -> bool:
        return bool(os.environ.get("MINTA_EVAL_LLM_BASE") or os.environ.get("MINTA_EVAL_LLM_KEY"))

    def query_vector(self, text: str):
        """Embed the original query; None when no embedder is attached."""
        if _EMBED_FN is None:
            return None
        try:
            return _EMBED_FN(text)
        except Exception:
            logger.exception("query embedding failed (falling back)")
            return None

    def recall_query_vector(self, text: str):
        """First-person recall query vector (gpt-4o-mini rewrite), or None."""
        if _EMBED_FN is None:
            return None
        from eval_recall import rewrite_recall_query  # LLM path, only when enabled

        try:
            rewritten = rewrite_recall_query(text)
        except Exception:
            logger.exception("recall-query rewrite failed (skipping channel)")
            return None
        if not rewritten:
            return None
        try:
            return _EMBED_FN(rewritten)
        except Exception:
            return None
