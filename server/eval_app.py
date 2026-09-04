"""AMC Add/Search evaluation app — standalone factory app.

Implements the memory-system side of the Agent Memory Leaderboard contract:

    POST /add      synchronous ingest; returns 200 only after every message is
                   durable and searchable; request_id idempotent
    POST /search   returns ranked, user-scoped evidence for a query
                   (never generates an answer)
    GET  /health   liveness

Only the eval plane is loaded (eval_store + retrieval/embed helpers). It never
imports the business `main:app`, routers, auth or the lifecycle auto-scanner,
so the evaluation container gets a clean, deterministic process.

Run (repo root, matching the Docker CMD):

    uvicorn server.eval_app:create_eval_app --factory --host 0.0.0.0 --port 8000

Logging discipline: no request bodies, memory content, queries or keys are
logged — only non-sensitive startup / error lines.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from eval_store import EvalStore  # noqa: E402

logger = logging.getLogger("minta.eval")


# ── contract schemas ───────────────────────────────────────────────────────

class AddMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_000_000)
    timestamp: Optional[int] = None  # Unix ms


class AddRequestModel(BaseModel):
    request_id: str = Field(min_length=1, max_length=256)
    messages: List[AddMessage] = Field(min_length=1, max_length=1000)
    user_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)


class AddResponse(BaseModel):
    success: bool = True
    request_id: str
    user_id: str
    session_id: str


class SearchRequestModel(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    options: Optional[List[str]] = None
    user_id: str = Field(min_length=1, max_length=256)
    top_k: int = Field(default=100, ge=1)  # clamped to 100 internally


class SearchHit(BaseModel):
    id: str
    content: str
    score: Optional[float] = None
    created_at: Optional[str] = None


class SearchResponse(BaseModel):
    data: List[SearchHit]


# ── app factory ────────────────────────────────────────────────────────────

def create_eval_app(db_url: str | None = None, embed_fn=None) -> FastAPI:
    """Build the eval app.

    `db_url` overrides MINTA_EVAL_DB (tests only). `embed_fn(content) -> bytes`
    attaches the (lazy, local) embedding model; None keeps /add fully
    offline-capable — every message is still stored losslessly and searchable
    via the recency fallback until vectors exist.
    """
    store = EvalStore(db_url)

    ttl = int(os.environ.get("MINTA_EVAL_TTL_HOURS", "720") or 0)
    try:
        store.ttl_cleanup(ttl)
    except Exception:
        logger.exception("eval ttl cleanup failed (continuing)")

    app = FastAPI(title="Minta — AMC eval adapter", docs_url=None, redoc_url=None)
    app.state.store = store

    # Canonical embed interface: fn(content) -> np.float32 vector. Storage
    # needs bytes, retrieval needs the array — bridge here.
    import numpy as _np

    injected_embed = embed_fn
    embed_state = {"off": False, "single": None, "batch": None}

    def _to_bytes(content: str) -> bytes:
        return _np.asarray(injected_embed(content), dtype=_np.float32).tobytes()

    def _to_bytes_batch(contents: list[str]) -> list[bytes]:
        # injected embedders are single-text callables; batch = loop here
        return [_to_bytes(c) for c in contents]

    def _init_local_embedder() -> bool:
        """Load the local model once; returns True when vectors are usable."""
        if embed_state["off"]:
            return False
        try:
            from eval_embed import embed_text, embed_texts
            from eval_experiments import set_embed_fn as _register

            _register(embed_text)
            embed_state["single"] = lambda c: _np.asarray(
                embed_text(c), dtype=_np.float32).tobytes()
            embed_state["batch"] = lambda cs: [
                _np.asarray(v, dtype=_np.float32).tobytes()
                for v in embed_texts(list(cs))]
            return True
        except Exception:
            embed_state["off"] = True
            logger.exception(
                "embedder init failed — embeddings disabled for this run "
                "(Add stays lossless; Search uses recency fallback)")
            return False

    def resolve_embed():
        """(single, batch) embed callables for this Add, or None when off."""
        if injected_embed is not None:
            return _to_bytes, _to_bytes_batch
        if embed_state["single"] is not None:
            return embed_state["single"], embed_state["batch"]
        if os.environ.get("MINTA_EVAL_EMBED", "1").lower() in ("0", "false", "off"):
            embed_state["off"] = True
            return None, None
        if not _init_local_embedder():
            return None, None
        return embed_state["single"], embed_state["batch"]

    @app.post("/add")
    def add(payload: AddRequestModel) -> AddResponse:
        try:
            single_fn, batch_fn = resolve_embed()
            # Batch path is DISABLED by default: measured stall on full runs
            # after the first conversation (threads/encode deadlock). Single
            # per-message encode is slower but proven over 861-question runs.
            # Re-enable for experiments with MINTA_EVAL_EMBED_BATCH=1.
            if os.environ.get("MINTA_EVAL_EMBED_BATCH", "0").lower() not in ("1", "true", "on"):
                batch_fn = None
            status, _n = store.add_batch(
                payload.request_id,
                payload.user_id,
                payload.session_id,
                [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
                 for m in payload.messages],
                embed_fn=single_fn,
                embed_batch_fn=batch_fn,
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("add ingest failed")
            raise HTTPException(status_code=503, detail={"reason": "ingest failed"})
        # duplicate and fresh both echo the request fields byte-identically
        return AddResponse(
            success=True,
            request_id=payload.request_id,
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

    @app.post("/search")
    def search(payload: SearchRequestModel) -> SearchResponse:
        from eval_retrieval import retrieve  # local import keeps /add path lean
        hits = retrieve(store, payload.query, payload.user_id,
                        top_k=payload.top_k, options=payload.options)
        return SearchResponse(data=hits)

    @app.get("/health")
    @app.get("/ping")
    def health() -> dict:
        return {"ok": True}

    return app
