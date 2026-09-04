"""gpt-4o-mini first-person recall-query rewrite (experiment arm, default off).

Benchmark questions are often third-person ("What city does Caroline currently
live in?") while the stored conversation is first-person ("I moved to
Seattle"). Rephrasing into the user's own register before embedding addresses
that register mismatch; the fusion is done in eval_retrieval with
MINTA_EVAL_RECALL_WEIGHT (default 0.5).

Only invoked when MINTA_EVAL_RECALL_QUERY=1 AND LLM env is configured, so the
default offline baseline never touches a network. Credential discipline:
MINTA_EVAL_LLM_KEY is read from env only — never logged, never committed.
The rewrite prompt below is our own wording, not copied from any participant.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger("minta.eval.recall")

# No module-level caches: a cross-request cache would look like shared state
# across evaluation samples (AML red line), even though it holds no memory.

_SYSTEM = (
    "You help a memory retrieval system. The stored log is written in the "
    "user's own first-person voice (\"I ...\", \"my ...\"). Rephrase the given "
    "question as a memory-check question the user would ask about what they "
    "themselves said or experienced earlier. Keep every name, place, date and "
    "detail. Output ONLY the rephrased question, nothing else."
)


def _endpoint() -> str:
    base = (os.environ.get("MINTA_EVAL_LLM_BASE") or "https://api.openai.com/v1").rstrip("/")
    return f"{base}/chat/completions"


def _model() -> str:
    return os.environ.get("MINTA_EVAL_LLM_MODEL") or "gpt-4o-mini"


def rewrite_recall_query(question: str) -> str | None:
    """First-person rewrite of `question`, or None when unavailable/failed."""
    api_key = os.environ.get("MINTA_EVAL_LLM_KEY", "")
    if not api_key:
        return None
    body = json.dumps({
        "model": _model(),
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": question},
        ],
        "temperature": 0,
        "max_tokens": 200,
    }).encode("utf-8")
    req = urllib.request.Request(
        _endpoint(), data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("recall-query rewrite call failed")
        return None
    text = text.strip().strip('"')
    if not text:
        return None
    return text
