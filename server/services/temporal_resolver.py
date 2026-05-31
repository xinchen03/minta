"""Temporal Resolver — time-aware query interpretation.

Distilled from Mem0 v3: parses relative time expressions ("last week",
"3 months ago", "upcoming") into absolute date ranges, anchors searches
to reference dates for reproducible time-aware retrieval.

Zero LLM cost. Pure pattern matching + date arithmetic.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Relative time patterns (English + Chinese)
_PATTERNS = [
    # English
    (r"(\d+)\s+days?\s+ago", lambda n: timedelta(days=int(n))),
    (r"(\d+)\s+weeks?\s+ago", lambda n: timedelta(weeks=int(n))),
    (r"(\d+)\s+months?\s+ago", lambda n: timedelta(days=int(n) * 30)),
    (r"(\d+)\s+years?\s+ago", lambda n: timedelta(days=int(n) * 365)),
    (r"last\s+week", lambda _: timedelta(weeks=1)),
    (r"last\s+month", lambda _: timedelta(days=30)),
    (r"last\s+year", lambda _: timedelta(days=365)),
    (r"yesterday", lambda _: timedelta(days=1)),
    (r"today", lambda _: timedelta(days=0)),
    (r"now|current(ly)?|right\s+now|upcoming|next", lambda _: timedelta(days=0)),
    (r"this\s+week", lambda _: timedelta(days=7)),
    (r"this\s+month", lambda _: timedelta(days=30)),
    # Chinese
    (r"(\d+)\s*天前", lambda n: timedelta(days=int(n))),
    (r"(\d+)\s*周前", lambda n: timedelta(weeks=int(n))),
    (r"(\d+)\s*个?月前", lambda n: timedelta(days=int(n) * 30)),
    (r"(\d+)\s*年前", lambda n: timedelta(days=int(n) * 365)),
    (r"上周", lambda _: timedelta(weeks=1)),
    (r"上个月", lambda _: timedelta(days=30)),
    (r"去年", lambda _: timedelta(days=365)),
    (r"昨天", lambda _: timedelta(days=1)),
    (r"今天|现在|当前|最近|接下来|即将", lambda _: timedelta(days=0)),
    (r"本周|这周", lambda _: timedelta(days=7)),
    (r"本月|这个月", lambda _: timedelta(days=30)),
]


def resolve_time_range(
    query: str,
    reference_date: Optional[datetime] = None,
) -> Optional[Tuple[datetime, datetime]]:
    """Parse query for relative time expressions, return (start, end) range.

    Args:
        query: Natural language query ("What did I do last week?")
        reference_date: Anchor date (defaults to now)

    Returns:
        (start_date, end_date) tuple or None if no time expression found.
    """
    if reference_date is None:
        reference_date = datetime.now()

    for pattern, delta_fn in _PATTERNS:
        m = re.search(pattern, query, re.IGNORECASE)
        if m:
            n = int(m.group(1)) if m.lastindex and m.group(1) and m.group(1).isdigit() else 0
            delta = delta_fn(n) if callable(delta_fn) else delta_fn
            start = reference_date - delta
            end = reference_date
            return (start, end)

    return None


def has_time_expression(query: str) -> bool:
    """Check if query contains any relative time expression."""
    for pattern, _ in _PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return True
    return False
