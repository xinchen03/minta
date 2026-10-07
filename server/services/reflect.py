"""Reflection service — detect correction signals and route to slots.

Signal types → Slot mapping:
  correction  (不是/不对/错了/不要)  → counter_examples
  preference  (应该/下次/以后/记得)  → preferences
  pending     (还没/todo/待办)       → pending
  knowledge   (文件操作/架构提及)      → knowledge
"""
from __future__ import annotations
import re
import logging
from datetime import datetime
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session as DBSession
from models.slot import Slot
from models.audit_log import record_audit
from services.privacy import filter_sensitive

logger = logging.getLogger(__name__)

# ── Signal patterns ──
SIGNAL_PATTERNS = [
    # (regex, signal_type, confidence_boost)
    # Correction signals → counter_examples
    (r"(?:不是|不对|错了|不要|别|停止|别再|不能这[样么]|不应该|不许)",
     "correction", 0.1),
    (r"(?:正确|应该是|应该是这样|正确的是|对的|没错)",
     "correction", -0.1),  # positive confirmation (downgrades correction)
    # Preference signals → preferences
    (r"(?:应该|最好|推荐|建议|倾向于|习惯|喜欢|偏好|以后|下次|记得|别忘了)",
     "preference", 0.05),
    (r"(?:用|采用|选择|优先).*?(?:而不是|而非|不要用|别用)",
     "preference", 0.15),
    # Pending signals → pending
    (r"(?:还没|还没做|todo|TODO|待办|未完成|还没完成|接下来|下一步|还需要|还差)",
     "pending", 0.1),
    # Knowledge signals → knowledge
    (r"(?:src/|lib/|api/|config|middleware|数据库|database|MySQL|Postgres|部署|deploy)",
     "knowledge", 0.05),
    # ── English patterns (parity with the counter-capture signal table) ──
    # Correction signals → counter_examples
    (r"\b(?:wrong|incorrect|not right|mistake|no longer|not anymore|correction|that'?s not (?:right|correct))\b",
     "correction", 0.1),
    (r"\b(?:should be|i meant|we meant|changed to|changed from|switch(?:ed)? to|moved to|migrated to|renamed to|replaced by|deprecated|is now|are now)\b",
     "correction", 0.1),
    (r"\b(?:redo|rewrite|do it again|fix it|don'?t do that|do not do that|stop doing)\b",
     "correction", 0.05),
    # Preference signals → preferences
    (r"\b(?:from now on|remember to|don'?t forget|i prefer|we prefer|always use|never use)\b",
     "preference", 0.05),
    # Pending signals → pending
    (r"\b(?:to-?do|next step|still need|not done|remaining)\b",
     "pending", 0.1),
]

SLOT_FOR_SIGNAL = {
    "correction": "counter_examples",
    "preference": "preferences",
    "pending": "pending",
    "knowledge": "knowledge",
}

# Max chars per slot entry (keep it tight)
MAX_ENTRY_CHARS = 300

# English function words excluded from correction-overlap matching: they carry
# no topical signal and would create spurious hits between unrelated texts.
_EN_STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "not", "but", "you", "all",
    "with", "this", "that", "from", "they", "have", "has", "had", "will",
    "would", "could", "should", "been", "its", "our", "their", "them",
    "then", "than", "when", "what", "which", "while", "there", "here",
    "where", "your", "does", "did", "doing", "done", "also", "too", "very",
    "into", "over", "under", "about", "after", "before", "because", "just",
    "dont", "doesnt", "didnt", "isnt", "arent", "wasnt", "werent", "cant",
    "wont", "couldnt", "shouldnt", "wouldnt", "hasnt", "havent",
}


def detect_signals(text: str) -> List[dict]:
    """Scan text for correction/preference/pending signals.

    Returns list of {type, confidence, matched_text, suggested_entry}.
    """
    if not text:
        return []

    signals = []
    for pattern, sig_type, boost in SIGNAL_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for m in matches:
            # Extract context around the match (up to 200 chars)
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 120)
            context = text[start:end].strip()

            confidence = min(1.0, 0.7 + boost)
            signals.append({
                "type": sig_type,
                "confidence": round(confidence, 2),
                "matched": m.group(),
                "context": context[:MAX_ENTRY_CHARS],
                "suggested": f"[auto] {context[:MAX_ENTRY_CHARS - 8]}",
            })

    # Deduplicate: keep highest confidence per type+similar context
    seen = set()
    unique = []
    for s in sorted(signals, key=lambda x: x["confidence"], reverse=True):
        key = (s["type"], s["context"][:60])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:20]  # max 20 signals per scan


def _append_to_slot(db: DBSession, user_id: int, slot_label: str, entry_text: str,
                    signal_type: str,
                    audit_action: str = "reflect.route_to_slot") -> Optional[str]:
    """Append one entry to a slot (dedup + size limit + audit).

    Returns the filtered entry text that was written, or None when nothing was
    written (missing slot, sensitive-filtered, or near-duplicate).
    """
    slot = db.query(Slot).filter(
        Slot.user_id == user_id,
        Slot.label == slot_label,
    ).first()

    if not slot:
        return None

    entry = filter_sensitive(entry_text.strip())
    if not entry:
        return None

    # Check if similar entry already exists (simple overlap check)
    existing_lines = slot.content.lower()
    if entry.lower()[:50] in existing_lines:
        return None  # near-duplicate

    # Append to slot
    sep = "\n" if slot.content and not slot.content.endswith("\n") else ""
    new_content = f"{slot.content}{sep}- {entry}"

    # Apply size limit
    if len(new_content) > slot.size_limit:
        from services.retention import smart_trim
        new_content, _ = smart_trim(new_content, slot.size_limit, db, user_id, slot_label)

    slot.content = new_content
    slot.auto_reflected = True
    db.commit()

    record_audit(db, user_id, "reflect", audit_action, "slot", [str(slot.id)], {
        "slotLabel": slot_label,
        "signalType": signal_type,
        "entryLen": len(entry),
    })

    return entry


def route_to_slot(
    db: DBSession,
    user_id: int,
    signal_type: str,
    entry_text: str,
) -> Tuple[Optional[str], bool]:
    """Route a detected signal to the appropriate slot.

    Returns (slot_label, was_appended).
    """
    slot_label = SLOT_FOR_SIGNAL.get(signal_type)
    if not slot_label:
        return None, False

    # Rules slot is updated by Expert promotion cycle, not signal routing
    if slot_label == "rules":
        return None, False

    entry = _append_to_slot(db, user_id, slot_label, entry_text, signal_type)
    if entry is None:
        return slot_label, False

    # Also create inbox item so user can review in InboxPanel
    try:
        from models.inbox import InboxItem
        inbox_entry = InboxItem(
            user_id=user_id,
            text=f"[{signal_type}] {entry}",
            confidence=0.65,  # auto-reflected = lower confidence
            status="pending",
            tags=[f"auto_reflected", f"slot:{slot_label}"],
        )
        db.add(inbox_entry)
        db.commit()
    except Exception:
        pass  # inbox write is best-effort, don't block slot update

    # If correction signal, find contradicted context objects and adjust confidence
    if signal_type == "correction":
        _apply_counter_to_context(db, user_id, entry)

    return slot_label, True


def _apply_counter_to_context(db: DBSession, user_id: int, counter_text: str,
                              exclude_ids: Optional[set] = None) -> int:
    """When a correction signal is detected, search for context objects
    that may be contradicted and decrement their confidence.

    Uses bilingual keyword overlap (CJK runs + English words) to find
    potentially contradicted objects. `exclude_ids` skips objects that are
    themselves part of the correction (e.g. the just-confirmed inbox object).
    Returns number of objects affected.
    """
    from models.context_object import ContextObject
    import re, json

    normalized = counter_text.lower().replace("'", "").replace("’", "")
    tokens = set(re.findall(r'[一-鿿]{2,}', counter_text))
    tokens |= {
        w for w in re.findall(r'[a-z0-9][a-z0-9_-]{2,}', normalized)
        if w not in _EN_STOPWORDS
    }
    if not tokens:
        return 0

    candidates = db.query(ContextObject).filter(
        ContextObject.user_id == user_id,
        ContextObject.status.in_(["active", "draft"]),
        ContextObject.confidence >= 3,
    ).all()

    affected = 0
    for obj in candidates:
        if exclude_ids and obj.id in exclude_ids:
            continue
        body = (obj.body or "") + " " + (obj.summary or "") + " " + (obj.title or "")
        if not body.strip():
            continue
        body_lower = body.lower()
        overlap = sum(1 for t in tokens if t.lower() in body_lower)
        if overlap >= 2:
            old_conf = obj.confidence
            obj.confidence = max(0, old_conf - 2)
            existing_tags = obj.tags or []
            if isinstance(existing_tags, str):
                try:
                    existing_tags = json.loads(existing_tags)
                except (json.JSONDecodeError, TypeError):
                    existing_tags = []
            if "countered" not in existing_tags:
                existing_tags.append("countered")
            obj.tags = existing_tags
            logger.info(
                f"Counter-example applied: object {obj.id} ({obj.title[:40]}) "
                f"confidence {old_conf} -> {obj.confidence} (overlap={overlap})"
            )
            affected += 1

    if affected:
        db.commit()
    return affected


def record_correction(db: DBSession, user_id: int, correction_text: str,
                      exclude_ids: Optional[set] = None) -> dict:
    """Record a confirmed correction and propagate it (best-effort).

    Called from the inbox confirm/archive path — the reachable moment where a
    user turns a pending item into memory. When the text carries a correction
    signal:
      1. overlapping active memories lose confidence and get tagged "countered"
      2. the correction is appended to the counter_examples slot, so it shows
         up under "Recent Lessons" in the next Context Pack

    Never raises; returns a summary dict for logging/tests.
    """
    result = {"detected": False, "affected": 0, "slot_updated": False}
    try:
        signals = detect_signals(correction_text)
        if not any(s["type"] == "correction" for s in signals):
            return result
        result["detected"] = True

        result["affected"] = _apply_counter_to_context(
            db, user_id, correction_text, exclude_ids=exclude_ids,
        )

        entry = f"[auto] {correction_text[:MAX_ENTRY_CHARS - 8]}"
        result["slot_updated"] = _append_to_slot(
            db, user_id, "counter_examples", entry, "correction",
            audit_action="reflect.record_correction",
        ) is not None
    except Exception as e:
        logger.warning(f"record_correction failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    return result


def reflect_session(
    db: DBSession,
    user_id: int,
    observations: List[dict],
) -> dict:
    """Run full reflection on a session's observations.

    observations: list of {type, content, tool_name, ...}

    Returns summary dict.
    """
    results: dict = {
        "signals_detected": 0,
        "slots_updated": [],
        "counter_examples": 0,
        "preferences": 0,
        "pending": 0,
        "knowledge": 0,
    }

    for obs in observations:
        content = obs.get("content", "") or obs.get("tool_output", "") or ""
        if not content:
            continue

        signals = detect_signals(content)
        results["signals_detected"] += len(signals)

        for sig in signals:
            slot_label, applied = route_to_slot(
                db, user_id, sig["type"], sig["suggested"],
            )
            if applied and slot_label:
                results["slots_updated"].append(slot_label)
                if sig["type"] == "correction":
                    results["counter_examples"] += 1
                elif sig["type"] == "preference":
                    results["preferences"] += 1
                elif sig["type"] == "pending":
                    results["pending"] += 1
                elif sig["type"] == "knowledge":
                    results["knowledge"] += 1

    results["slots_updated"] = list(set(results["slots_updated"]))

    # ── Minta Expert: run promotion cycle + update rules slot ──
    try:
        from config import MINTA_EXPERT_ENABLED
        if MINTA_EXPERT_ENABLED:
            from services.rule_promotion import RulePromotionPipeline
            pipeline = RulePromotionPipeline(db)
            promo_report = pipeline.run_cycle(user_id)
            results["expert_promotion"] = promo_report.dict()

            # Auto-populate rules slot with compiled expert rules
            from services.production_store import list_rules as list_expert_rules
            expert_rules = list_expert_rules(db, user_id, stage=None, limit=20)
            if expert_rules:
                rules_slot = db.query(Slot).filter(
                    Slot.user_id == user_id,
                    Slot.label == "rules",
                ).first()
                if rules_slot:
                    lines = []
                    for r in expert_rules:
                        conf_pct = int(r.confidence * 100)
                        lines.append(
                            f"- [{r.domain}] {r.trigger} → {r.action} "
                            f"(conf={conf_pct}%, stage={r.stage})"
                        )
                    rules_slot.content = "\n".join(lines)
                    db.commit()
                    results["slots_updated"].append("rules")
    except Exception:
        pass

    logger.info(
        f"Reflection done for user {user_id}: "
        f"{results['signals_detected']} signals, "
        f"{len(results['slots_updated'])} slots updated"
    )
    return results
