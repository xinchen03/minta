"""Lazy local embedder for the eval plane (sentence-transformers, no Chroma).

Model resolution order:
    MINTA_EVAL_EMBED_MODEL > MINTA_EMBEDDING_MODEL > sentence-transformers/all-mpnet-base-v2

The Docker image pins the model to a baked /models path at build time; local
proxy runs set MINTA_EVAL_EMBED_MODEL=D:/all-mpnet-base-v2 (the weights used by
Minta-next's historical LoCoMo numbers, so proxy scores stay comparable).
Loading happens once, on the first call, behind a lock.
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

logger = logging.getLogger("minta.eval.embed")

_lock = threading.Lock()
_model = None
_model_path = None


def _resolve_path() -> str:
    return (os.environ.get("MINTA_EVAL_EMBED_MODEL")
            or os.environ.get("MINTA_EMBEDDING_MODEL")
            or "sentence-transformers/all-mpnet-base-v2")


def embed_text(text: str) -> np.ndarray:
    """Encode one text to a normalized float32 vector (768d for mpnet)."""
    global _model, _model_path
    path = _resolve_path()
    if _model is None or _model_path != path:
        with _lock:
            if _model is None or _model_path != path:
                from sentence_transformers import SentenceTransformer

                logger.info("loading eval embedder: %s", path)
                _model = SentenceTransformer(path)
                _model_path = path
    v = _model.encode(text, normalize_embeddings=True)
    arr = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    if n > 0:
        arr = arr / n
    return arr
