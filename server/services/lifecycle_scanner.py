"""Lifecycle Scanner — detect memory quality issues without auto-executing.

All findings go to inbox for human review. Nothing is changed automatically.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Dict, Optional
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import and_, or_
from models.context_object import ContextObject

logger = logging.getLogger(__name__)

# ── Thresholds ──
STALE_DAYS = 30          # warn if not accessed in N days
REDUNDANCY_RATIO = 0.80  # title/summary similarity threshold
FRAGMENT_MIN_COUNT = 3   # min objects sharing a tag to flag fragmentation


def similarity(a: str, b: str) -> float:
    """0.0–1.0 text similarity via SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def scan_staleness(db: DBSession, user_id: int) -> List[Dict]:
    """Find active contexts untouched for > STALE_DAYS."""
    cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
    stale = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.status == "active",
        ContextObject.type != "rule",  # skip expert rules
        or_(
            ContextObject.last_used_at < cutoff,
            and_(ContextObject.last_used_at.is_(None), ContextObject.updated_at < cutoff),
        ),
    ).order_by(ContextObject.updated_at.asc()).limit(20).all()

    findings = []
    for obj in stale:
        last = obj.last_used_at or obj.updated_at
        days = (datetime.utcnow() - last).days if last else "?"
        findings.append({
            "type": "staleness",
            "severity": "medium",
            "object_id": obj.id,
            "title": obj.title,
            "days_since_last_use": days,
            "suggestion": f"「{obj.title}」已 {days} 天未使用，建议审查是否仍需保留。",
        })
    return findings


def scan_redundancy(db: DBSession, user_id: int) -> List[Dict]:
    """Find context pairs with highly similar titles or summaries."""
    objects = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.status == "active",
        ContextObject.type != "rule",
    ).order_by(ContextObject.updated_at.desc()).limit(100).all()

    findings = []
    n = len(objects)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = objects[i], objects[j]
            title_sim = similarity(a.title, b.title)
            summary_sim = similarity(a.summary or "", b.summary or "")
            best = max(title_sim, summary_sim)

            if best >= REDUNDANCY_RATIO and title_sim < 0.98:  # skip exact dupes
                findings.append({
                    "type": "redundancy",
                    "severity": "low",
                    "object_ids": [a.id, b.id],
                    "titles": [a.title, b.title],
                    "similarity": round(best, 2),
                    "suggestion": f"「{a.title}」与「{b.title}」相似度 {best:.0%}，建议合并或保留一条。",
                })

    # Limit findings
    findings.sort(key=lambda f: -f["similarity"])
    return findings[:10]


def scan_fragmentation(db: DBSession, user_id: int) -> List[Dict]:
    """Find tags shared by many objects — potential fragmentation."""
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT tags FROM context_objects WHERE user_id = :uid AND status = 'active' AND type != 'rule'"
    ), {"uid": user_id}).fetchall()

    # Count tag usage
    tag_counts: Dict[str, int] = {}
    tag_objects: Dict[str, List[str]] = {}
    import json
    for (tags_raw,) in rows:
        try:
            tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
        except (json.JSONDecodeError, TypeError):
            continue
        for tag in tags:
            tag = tag.strip().lower()
            if len(tag) < 3 or tag in ("onboarding", "starter", "sample", "autopilot"):
                continue
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Get objects for high-count tags
    findings = []
    for tag, count in tag_counts.items():
        if count >= FRAGMENT_MIN_COUNT:
            objs = db.query(ContextObject).filter(
                ContextObject.user_id == user_id,
                ContextObject.tags.contains(tag),
                ContextObject.status == "active",
            ).limit(10).all()
            findings.append({
                "type": "fragmentation",
                "severity": "low",
                "tag": tag,
                "object_count": count,
                "object_ids": [o.id for o in objs[:5]],
                "titles": [o.title for o in objs[:5]],
                "suggestion": f"标签「{tag}」下有 {count} 条 context，可能碎片化了。建议审查是否应整合。",
            })

    return findings[:5]


# ── Conflict Detection ──
CONFLICT_MIN_SIM = 0.25   # minimum semantic similarity to consider related
CONFLICT_MAX_SIM = 0.75   # above this = too similar (redundancy territory)

# Heuristic contradiction patterns: (marker_a, marker_b)
_CONTRADICT_PATTERNS = [
    (["use ", "using ", "adopt ", "switch to ", "prefer ", "recommend "],
     ["avoid ", "stop using ", "deprecate ", "migrate from ", "don't use "]),
]

# Negation words that flip meaning
_NEGATION_WORDS = {"not", "never", "no", "don't", "cannot", "can't", "won't", "shouldn't"}


def _extract_key_phrases(text: str) -> list:
    """Extract technology/tool/method recommendations from text (EN + ZH)."""
    import re

    pos_en = ["use ", "using ", "adopt ", "switch to ", "prefer ", "recommend "]
    pos_zh = ["用", "使用", "采用", "统一用", "推荐", "建议用", "首选", "选择", "迁移到"]
    neg_en = ["avoid ", "stop using ", "don't use ", "deprecate ", "migrate from "]
    neg_zh = ["不用", "避免", "不要用", "不建议", "弃用", "停止使用", "不推荐"]

    phrases = []
    text_lower = text.lower()

    for ind in pos_en + neg_en:
        idx = text_lower.find(ind)
        if idx >= 0:
            rest = text[idx + len(ind):].strip().rstrip(".,;!?，。；！")
            if len(rest) >= 2:
                phrases.append(ind.strip() + " " + rest[:80])

    for ind in pos_zh + neg_zh:
        idx = text.find(ind)
        if idx >= 0:
            end = min(idx + len(ind) + 80, len(text))
            rest = text[idx + len(ind): end].strip().rstrip(".,;!?，。；！")
            if len(rest) >= 1:
                phrases.append(ind + " " + rest)

    return phrases


def _detect_contradiction(obj_a: ContextObject, obj_b: ContextObject) -> Optional[Dict]:
    """Check if two context objects appear to make contradictory claims.

    Uses a two-layer approach:
    1. Tag overlap: if they share tags, they're about the same domain
    2. Phrase comparison: if their extracted recommendations differ, flag conflict
    """
    text_a = f"{obj_a.title} {obj_a.summary or ''} {obj_a.body or ''}"[:500]
    text_b = f"{obj_b.title} {obj_b.summary or ''} {obj_b.body or ''}"[:500]

    phrases_a = _extract_key_phrases(text_a)
    phrases_b = _extract_key_phrases(text_b)

    if not phrases_a or not phrases_b:
        return None

    # Check if they share tags (same domain)
    def _to_tags(tags_val):
        if tags_val is None:
            return set()
        if isinstance(tags_val, list):
            return set(tags_val)
        if isinstance(tags_val, str):
            try:
                return set(json.loads(tags_val))
            except (json.JSONDecodeError, TypeError):
                return {t.strip() for t in tags_val.split(",") if t.strip()}
        return set()

    import json
    tags_a = _to_tags(obj_a.tags)
    tags_b = _to_tags(obj_b.tags)
    shared_tags = tags_a & tags_b

    pos_words = ["use", "using", "adopt", "switch to", "prefer", "recommend",
                  "用", "使用", "采用", "统一用", "推荐", "建议用", "首选", "迁移到"]
    neg_words = ["avoid", "stop using", "don't use", "deprecate", "migrate from",
                  "不用", "避免", "不要用", "不建议", "弃用", "停止使用", "不推荐"]

    for pa in phrases_a:
        for pb in phrases_b:
            pa_pos = any(pa.lower().startswith(w) for w in pos_words)
            pb_pos = any(pb.lower().startswith(w) for w in pos_words)
            pa_neg = any(pa.lower().startswith(w) for w in neg_words)
            pb_neg = any(pb.lower().startswith(w) for w in neg_words)

            # Type 1: one positive, one negative about shared tags
            if (pa_pos and pb_neg) or (pa_neg and pb_pos):
                if shared_tags:
                    return {
                        "type": "conflict",
                        "severity": "high",
                        "object_ids": [obj_a.id, obj_b.id],
                        "titles": [obj_a.title, obj_b.title],
                        "conflict_type": "recommendation_vs_avoidance",
                        "phrase_a": pa[:80],
                        "phrase_b": pb[:80],
                        "shared_tags": list(shared_tags)[:3],
                        "suggestion": (
                            f"「{obj_a.title}」建议「{pa[:50]}」，"
                            f"但「{obj_b.title}」建议「{pb[:50]}」——"
                            f"两条 context 共享标签 {list(shared_tags)[:3]}，可能矛盾。"
                        ),
                    }

            # Type 2: both recommend but different, and share tags
            if pa_pos and pb_pos:
                if shared_tags:
                    # Extract the "what" from each phrase (strip the indicator)
                    what_a = pa
                    what_b = pb
                    for w in pos_words:
                        what_a = what_a.replace(w, "", 1) if what_a.startswith(w) else what_a
                        what_b = what_b.replace(w, "", 1) if what_b.startswith(w) else what_b
                    what_a = what_a.strip().rstrip(".,;!?，。；！")[:30]
                    what_b = what_b.strip().rstrip(".,;!?，。；！")[:30]

                    # Different recommendations about the same domain = conflict
                    if what_a.lower() != what_b.lower() and what_a and what_b:
                        return {
                            "type": "conflict",
                            "severity": "medium",
                            "object_ids": [obj_a.id, obj_b.id],
                            "titles": [obj_a.title, obj_b.title],
                            "conflict_type": "competing_recommendations",
                            "phrase_a": pa[:80],
                            "phrase_b": pb[:80],
                            "shared_tags": list(shared_tags)[:3],
                            "suggestion": (
                                f"「{obj_a.title}」推荐「{what_a}」，"
                                f"而「{obj_b.title}」推荐「{what_b}」——"
                                f"两者共享标签 {list(shared_tags)[:3]}，可能不兼容。"
                            ),
                        }

    return None


def scan_conflict(db: DBSession, user_id: int) -> List[Dict]:
    """Find context pairs that appear to make contradictory claims.

    Uses a two-stage approach:
    1. Find candidate pairs via embedding similarity (moderate range)
    2. Apply heuristic contradiction detection on text
    """
    objects = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.status == "active",
        ContextObject.type != "rule",
    ).order_by(ContextObject.updated_at.desc()).limit(80).all()

    if len(objects) < 3:
        return []

    findings = []
    n = len(objects)

    # Try embedding-based candidate filtering
    try:
        from services.embedding_service import embedding_service
        embeddings = embedding_service.embed_batch([
            f"{o.title} {o.summary or ''}"[:256] for o in objects
        ])
        import numpy as np
        emb_matrix = np.array(embeddings)
        norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        emb_matrix = emb_matrix / norms

        for i in range(n):
            for j in range(i + 1, n):
                sim = float(np.dot(emb_matrix[i], emb_matrix[j]))
                if CONFLICT_MIN_SIM <= sim <= CONFLICT_MAX_SIM:
                    result = _detect_contradiction(objects[i], objects[j])
                    if result:
                        result["embedding_similarity"] = round(sim, 2)
                        findings.append(result)
    except Exception:
        # Fallback: check all pairs (limited to 80 objects → 3160 pairs max)
        for i in range(n):
            for j in range(i + 1, n):
                result = _detect_contradiction(objects[i], objects[j])
                if result:
                    result["embedding_similarity"] = None
                    findings.append(result)

    findings.sort(key=lambda f: f["severity"] == "high", reverse=True)
    return findings[:10]


def scan_schema_validation(db: DBSession, user_id: int) -> List[Dict]:
    """Detect schema violations — empty body, type mismatch, duplicates."""
    objects = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.status == "active",
        ContextObject.type != "rule",
    ).all()

    findings = []
    title_counts = {}
    for obj in objects:
        t = (obj.title or "").strip().lower()
        if t:
            title_counts.setdefault(t, []).append(obj.id)

    for obj in objects:
        violations = []
        title = obj.title or ""
        body = (obj.body or "").strip()
        summary = (obj.summary or "").strip()

        if title and not body and not summary:
            violations.append("empty_body")
        if (obj.confidence or 3) < 3 and not body and not summary:
            violations.append("low_confidence_fragment")

        if violations:
            findings.append({
                "type": "schema_violation", "severity": "low",
                "object_id": obj.id, "title": title, "violations": violations,
                "suggestion": f"Schema issue in [{title[:60]}]: {', '.join(violations)}",
            })

    duplicate_ids = {id for ids in title_counts.values() if len(ids) >= 2 for id in ids}
    if duplicate_ids:
        findings.append({
            "type": "schema_violation", "severity": "low",
            "object_ids": list(duplicate_ids)[:10], "violations": ["duplicate_title"],
            "suggestion": f"{len(duplicate_ids)} objects share duplicate titles.",
        })

    return findings[:20]


def run_full_scan(db: DBSession, user_id: int) -> Dict:
    """Run all lifecycle scans and return aggregated findings.

    Does NOT modify any data. Caller decides what to do with findings.
    """
    findings = {
        "staleness": scan_staleness(db, user_id),
        "redundancy": scan_redundancy(db, user_id),
        "fragmentation": scan_fragmentation(db, user_id),
        "conflict": scan_conflict(db, user_id),
        "schema_violation": scan_schema_validation(db, user_id),
    }
    total = sum(len(v) for v in findings.values())
    logger.info(f"Lifecycle scan for user {user_id}: {total} findings "
                f"(stale={len(findings['staleness'])}, "
                f"redundant={len(findings['redundancy'])}, "
                f"fragmented={len(findings['fragmentation'])}, "
                f"conflict={len(findings['conflict'])}, "
                f"schema={len(findings['schema_violation'])})")
    return findings


def findings_to_inbox_items(findings: Dict, user_id: int) -> List[Dict]:
    """Convert scanner findings to inbox-ready items.

    Returns list of dicts ready for InboxItem creation.
    """
    items = []
    severity_confidence = {"high": 0.8, "medium": 0.6, "low": 0.4}

    for category, cat_findings in findings.items():
        for f in cat_findings:
            items.append({
                "user_id": user_id,
                "text": f["suggestion"],
                "type": "lesson_learned",
                "confidence": severity_confidence.get(f.get("severity", "low"), 0.4),
                "tags": ["lifecycle", category, "auto-detected"],
                "status": "pending",
            })

    return items
