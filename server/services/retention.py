"""Smart retention — trim slot content when exceeding sizeLimit.

Strategy: split content into logical entries (double-newline separated),
score each by recency × 0.7 + access × 0.3, keep top-K under limit.
Trimmed entries are archived (not deleted).
"""
from __future__ import annotations
import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session as DBSession
from models.archived_item import ArchivedItem
from models.audit_log import record_audit

logger = logging.getLogger(__name__)

SCORE_RECENCY_WEIGHT = 0.7
SCORE_ACCESS_WEIGHT = 0.3


def _score_entry(entry: str, entry_index: int, total_entries: int) -> float:
    """Score an entry by its position (proxy for recency — later entries are newer)."""
    recency = (entry_index + 1) / total_entries
    return recency * SCORE_RECENCY_WEIGHT + 0.3 * SCORE_ACCESS_WEIGHT


def smart_trim(
    content: str,
    size_limit: int,
    db: Optional[DBSession] = None,
    user_id: Optional[int] = None,
    slot_label: str = "",
) -> Tuple[str, Optional[str]]:
    """Trim content to fit size_limit. Returns (trimmed_content, archived_text_or_None).

    If db + user_id are provided, trimmed entries are archived.
    Otherwise, just truncation without archiving.
    """
    if len(content) <= size_limit:
        return content, None

    entries = [e.strip() for e in content.split("\n\n") if e.strip()]
    if not entries:
        return content[:size_limit], None

    scored = []
    total = len(entries)
    for i, entry in enumerate(entries):
        scored.append((_score_entry(entry, i, total), entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    kept = []
    kept_len = 0
    archived_entries = []

    for score, entry in scored:
        entry_len = len(entry) + 2  # +2 for "\n\n" separator
        if kept_len + entry_len <= size_limit:
            kept.append(entry)
            kept_len += entry_len
        else:
            archived_entries.append((score, entry))

    if not kept:
        kept.append(entries[-1][:size_limit])
        archived_entries = [(s, e) for s, e in scored if e != entries[-1]]

    trimmed = "\n\n".join(kept)
    archived_text = "\n\n".join(e for _, e in archived_entries) if archived_entries else None

    if db and user_id and archived_text:
        try:
            avg_score = sum(s for s, _ in archived_entries) / len(archived_entries)
            archived = ArchivedItem(
                user_id=user_id,
                slot_label=slot_label,
                content=archived_text,
                retention_score=round(avg_score, 3),
            )
            db.add(archived)
            db.commit()

            record_audit(db, user_id, "archive", "retention.smart_trim", "slot", [], {
                "slotLabel": slot_label,
                "archivedChars": len(archived_text),
                "keptChars": len(trimmed),
                "archivedEntries": len(archived_entries),
            })
        except Exception as e:
            logger.warning(f"Archive write failed (non-fatal): {e}")
            db.rollback()

    return trimmed, archived_text
