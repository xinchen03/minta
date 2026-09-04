"""AMC retrieval mainline: dense → seed → neighbour-window → dedupe → fill.

Fidelity-first (v3 design): evidence is the raw message with a minimal
role/timestamp envelope; the pipeline adds context (adjacent turns of the same
Add chunk, radius configurable) and fills `min(top_k, 100)` by default, based
on the public ablations of the cycle-1 #3 open-source system (ActiveMemoryIndex:
fill-top_k monotone accuracy, window radius 1 => LoCoMo .6333 -> .6802).

Governance knobs (decay/conflict/recency/re-ranker, etc.) deliberately live in
`eval_experiments` and stay OFF by default — nothing here rewrites content.

Retrieval isolation is structural: every query starts from
`store.memories_for_user(user_id)` and never sees another user's rows.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("minta.eval.retrieval")

_MAX_RETURN = 100  # contract top_k ceiling


# ── helpers ────────────────────────────────────────────────────────────────

def utc_iso(millis: Optional[int]) -> Optional[str]:
    if millis is None:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def envelope(row: dict, on: bool) -> str:
    """Minimal provenance wrapper; index/embedding always use raw content."""
    raw = row["raw_content"]
    if not on:
        return raw
    parts = []
    ts = utc_iso(row.get("timestamp_ms"))
    if ts:
        parts.append(f"[{ts}]")
    if row.get("role"):
        parts.append(f"{row['role']}: {raw}")
    return " ".join(parts) if parts else raw


def _created_at_iso(row: dict) -> Optional[str]:
    """created_at prefers the source timestamp; falls back to persist time."""
    ts = utc_iso(row.get("timestamp_ms"))
    if ts:
        return ts
    dt = row.get("created_at")
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _dense_scores(rows: list[dict], query_vec) -> dict[str, float]:
    """Cosine similarity per memory id over stored float32 vectors.

    Returns {} when no row carries an embedding (offline baseline arm) — the
    caller then falls back to recency ordering.
    """
    import numpy as np

    q = np.asarray(query_vec, dtype=np.float32)
    qn = np.linalg.norm(q)
    if qn == 0:
        return {}
    q = q / qn
    scores: dict[str, float] = {}
    for r in rows:
        blob = r.get("embedding")
        if not blob:
            continue
        v = np.frombuffer(blob, dtype=np.float32)
        if v.size != q.size:
            continue
        n = float(np.linalg.norm(v))
        scores[r["id"]] = float(np.dot(q, v)) / n if n else 0.0
    return scores


def _recency_key(row: dict):
    """Newest first; persists across restarts (deterministic ties by id)."""
    return (-(row.get("timestamp_ms") or 0), row["created_at"] or datetime.min,
            row["request_id"], row["msg_index"])


def _apply_query_tense_recency(query: str, kept: list[dict], scores: dict) -> None:
    """Minta governance at the evidence level: query-tense aware latest-first.

    Group memories into same-fact clusters (token-Jaccard on raw content);
    for 'current' questions nudge the newest member up, for 'past' questions
    nudge the oldest member up. Pure re-ranking — nothing is rewritten,
    deleted or hidden (memory-debt: old accounts stay audit-ready).
    """
    import re

    ql = query.lower()
    current = any(t in ql for t in ("now", "currently", "current", "prefers",
                                    "latest", "these days", "still", "is the"))
    past = any(t in ql for t in ("before", "used to", "previously",
                                 "originally", "earlier", "ago", "was the",
                                 "past", "old "))
    if not (current or past):
        return

    def toks(s: str) -> set:
        return {w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) > 2}

    clusters: list[list[dict]] = []
    for r in kept:
        rt = toks(r["raw_content"])
        if not rt:
            continue
        for cl in clusters:
            j = len(rt & toks(cl[0]["raw_content"])) / max(len(rt) + len(toks(cl[0]["raw_content"])) - len(rt & toks(cl[0]["raw_content"])), 1)
            if j >= 0.6:
                cl.append(r)
                break
        else:
            clusters.append([r])
    boost = 0.12
    for cl in clusters:
        if len(cl) < 2:
            continue
        cl_sorted = sorted(cl, key=lambda r: -(r.get("timestamp_ms") or 0))
        target = cl_sorted[0] if current else cl_sorted[-1]
        scores[target["id"]] = scores.get(target["id"], 0.0) + boost


# ── mainline ───────────────────────────────────────────────────────────────

def retrieve(store, query: str, user_id: str, top_k: int = 100,
             options: Optional[list[str]] = None) -> list[dict]:
    """Return evidence hits for one user, ordered best-first, ≤ min(top_k,100).

    Result entries: {id, content(enveloped), score?, created_at?}.
    Never generates an answer.
    """
    target = max(1, min(top_k, _MAX_RETURN))
    rows = store.memories_for_user(user_id)
    if not rows:
        return []

    from eval_experiments import experiments  # env-gated arms, all default-off

    exp = experiments()

    # dedupe suppression first (lossless store, retrieval-side suppression)
    kept: list[dict] = []
    seen_hashes: set[str] = set()
    for r in rows:
        h = _content_hash(r["raw_content"])
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        kept.append(r)

    # channel scores
    scores: dict[str, float] = {}
    qv = exp.query_vector(query)
    if qv is not None:
        scores.update(_dense_scores(kept, qv))
    if exp.bm25_enabled():
        scores = _fuse_bm25(kept, query, scores)
    if exp.recall_query_enabled():
        rqv = exp.recall_query_vector(query)
        if rqv is not None:
            rs = _dense_scores(kept, rqv)
            w = exp.recall_weight()
            for mid, s in rs.items():
                scores[mid] = (1.0 - w) * scores.get(mid, 0.0) + w * s
    if exp.options_enabled() and options:
        # MC option expansion: union of per-option dense scores. This only
        # widens evidence recall — it never judges which option is right.
        for opt in options:
            if not opt:
                continue
            ovec = exp.query_vector(opt)
            if ovec is None:
                continue
            for mid, s in _dense_scores(kept, ovec).items():
                if s > 0:  # only real option affinity lifts evidence
                    scores[mid] = max(scores.get(mid, -1.0), s)
    if exp.temporal_enabled():
        # Minta-native arm: query-conditioned temporal boost (retrieval
        # signal only — content is never rewritten). Active only when the
        # query carries a time expression that resolves to a range.
        from datetime import datetime as _dt, timezone as _tz
        from services.temporal_resolver import has_time_expression, resolve_time_range
        if has_time_expression(query):
            tr = resolve_time_range(query)
            if tr is not None:
                start, end = tr
                for r in kept:
                    ts = r.get("timestamp_ms")
                    if ts is None:
                        continue
                    try:
                        d = _dt.fromtimestamp(ts / 1000.0, tz=_tz.utc).replace(tzinfo=None)
                    except (OverflowError, OSError, ValueError):
                        continue
                    if start <= d <= end:
                        prox = max(0.0, 1.0 - abs((d - start).days) / 90.0)
                        scores[r["id"]] = max(scores.get(r["id"], -1.0),
                                              0.25 + 0.35 * prox)

    if exp.rerank_enabled():
        # Local cross-encoder re-orders the top dense candidates before the
        # window/fill stages (zero LLM). Kept as an experiment arm until proxy
        # evidence on the hard categories says it pays.
        from eval_rerank import rerank_scores

        rs = rerank_scores(query, kept, scores, n=60)
        if rs:
            scores = rs
    if exp.recencyq_enabled():
        # Minta governance at the evidence level (memory-debt semantics):
        # 'current' questions surface the newest member of each same-fact
        # cluster, 'past' questions surface the oldest. Ranking only.
        _apply_query_tense_recency(query, kept, scores)

    # seed order
    if scores:
        seeded = sorted(kept, key=lambda r: (-scores.get(r["id"], -1.0),
                                             _recency_key(r)))
    else:
        seeded = sorted(kept, key=_recency_key)  # offline fallback ordering

    radius = exp.window_radius()

    selected: list[dict] = []
    included: set[str] = set()

    def _add(row: dict):
        if row["id"] in included or len(selected) >= target:
            return False
        selected.append(row)
        included.add(row["id"])
        return True

    # seeds first, then neighbours of selected seeds, then remaining fillers
    if radius > 0:
        by_req: dict[str, dict[int, dict]] = {}
        for r in kept:
            by_req.setdefault(r["request_id"], {})[r["msg_index"]] = r
        for seed in seeded:
            if len(selected) >= target:
                break
            _add(seed)
            req = by_req.get(seed["request_id"], {})
            for step in range(1, radius + 1):
                if len(selected) >= target:
                    break
                for idx in (seed["msg_index"] - step, seed["msg_index"] + step):
                    nbr = req.get(idx)
                    if nbr is not None:
                        _add(nbr)
    else:
        for seed in seeded:
            if not _add(seed):
                break

    if len(selected) < target:
        for r in seeded:  # fillers, same global order as seeds
            if len(selected) >= target:
                break
            _add(r)

    if exp.timeorder_enabled() and _is_order_query(query):
        # Ordering-type questions ("list the order in which ...") need
        # chronological evidence, not relevance order. Conditional branch:
        # every other query is untouched.
        selected = sorted(selected, key=lambda r: r.get("timestamp_ms") or 0)

    hits = []
    for r in selected:
        hits.append({
            "id": r["id"],
            "content": envelope(r, exp.envelope_enabled()),
            "score": round(scores[r["id"]], 4) if r["id"] in scores else None,
            "created_at": _created_at_iso(r),
        })
    return hits


_ORDER_MARKERS = re.compile(
    r"\b(in order|order in which|chronolog|sequence|timeline|先后|依次"
    r"|earliest|first .{0,40}(then|later|after)|what order)\b",
    re.IGNORECASE)


def _is_order_query(query: str) -> bool:
    return bool(_ORDER_MARKERS.search(query or ""))


def _fuse_bm25(rows: list[dict], query: str, scores: dict[str, float]) -> dict[str, float]:
    """Reciprocal-rank fusion of an optional BM25 channel with current scores."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return scores
    corpus = [_tokenize(r["raw_content"]) for r in rows]
    if not any(corpus):
        return scores
    try:
        bm25 = BM25Okapi(corpus)
    except Exception:
        return scores
    tok_q = _tokenize(query)
    if not tok_q:
        return scores
    b_scores = bm25.get_scores(tok_q)
    ranked = sorted(range(len(rows)), key=lambda i: b_scores[i], reverse=True)
    k = 60
    for rank, i in enumerate(ranked[:len(rows)]):
        if b_scores[i] <= 0:
            continue
        oid = rows[i]["id"]
        fused = scores.get(oid, 0.0)
        scores[oid] = fused + 0.5 / (k + rank + 1)  # BM25 weight 0.5, A/B-able
    return scores


def _tokenize(text: str) -> list[str]:
    import re
    toks = re.findall(r"[a-zA-Z0-9_']+", text.lower())
    return [t for t in toks if len(t) > 1]
