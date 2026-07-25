#!/usr/bin/env python3
"""Counter-example candidate capture for UserPromptSubmit hook.

Detects potential correction signals in user messages, builds structured
CANDIDATE payloads, and enqueues them to the counter server (18720) with
local JSONL fallback. This module NEVER produces CONFIRMED counterexamples
-- it only flags candidates for later human or skill-based confirmation.

Design contract:
  - Hook MUST be fail-open: never block or error Claude Code
  - HTTP timeout <= 300ms
  - Failed POSTs fall back to local JSONL queue
  - Candidates are deduplicated by content hash
  - False positives are filtered aggressively (code, citations, hypotheticals)
  - No full conversation context, tokens, or credentials are persisted
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Optional

# -- Config resolver ------------------------------------------------------------

def _resolve_config() -> dict:
    """Resolve counter_capture config: env vars -> ~/.minta/config.json -> defaults."""
    cfg = {
        "enabled": True,
        "endpoint": "http://127.0.0.1:8772/api/inbox/append",
        "fallback_endpoint": "http://127.0.0.1:18720/api/counter/append",
        "fallback_queue": str(Path.home() / ".minta" / "counter" / "candidate-queue.jsonl"),
        "api_key": os.environ.get("MINTA_API_KEY", ""),
        "timeout_ms": 300,
    }

    # Layer 1: ~/.minta/config.json
    try:
        minta_cfg_path = Path.home() / ".minta" / "config.json"
        if minta_cfg_path.exists():
            minta_cfg = json.loads(minta_cfg_path.read_text(encoding="utf-8"))
            cc = minta_cfg.get("counter_capture", {})
            if isinstance(cc, dict):
                for k in cfg:
                    if k in cc:
                        cfg[k] = cc[k]
    except Exception:
        pass

    # Layer 2: Environment variables (highest priority)
    env_map = {
        "MINTA_COUNTER_ENABLED": ("enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "MINTA_COUNTER_ENDPOINT": ("endpoint", str),
        "MINTA_COUNTER_FALLBACK_QUEUE": ("fallback_queue", str),
        "MINTA_COUNTER_TIMEOUT_MS": ("timeout_ms", int),
    }
    for env_key, (cfg_key, cast) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            try:
                cfg[cfg_key] = cast(val)
            except (ValueError, TypeError):
                pass

    return cfg


_config = _resolve_config()

# -- Signal detection patterns --------------------------------------------------

# Each pattern: (regex, signal_type, confidence_boost)
# These identify CANDIDATE correction signals - they do NOT confirm a correction.

CORRECTION_PATTERNS = [
    # Explicit negations
    (r"(?:不是|不对|错了|你理解错了|搞错了|有问题|不行|不应该|不许|别再|不能这[样么])",
     "explicit_correction", 0.15),

    # Reformulation
    (r"(?:应该是|正确的是|我要的是|我说的是|我之前说的是|我的意思是|这里需要修正)",
     "explicit_correction", 0.20),

    # Entity / naming corrections
    (r"(?:不要把\s*\S+\s*当成|不叫|不是叫|改名|实际叫|正确的名字是|正式名称是)",
     "explicit_correction", 0.18),

    # State/fact corrections
    (r"(?:事实是|实际上|真实情况是|其实是|并不是|根本没有|不存在)",
     "explicit_correction", 0.12),

    # Missing constraint
    (r"(?:你应该先|要先|怎么不先|为什么不|要先做|先查|先读)",
     "missing_constraint", 0.10),

    # Preference correction (weaker)
    (r"(?:我更喜欢|我倾向|用.*?而不是|优先.*?而非|别用.*?改用)",
     "user_preference_correction", 0.05),

    # Frustration markers — 3+ consecutive question marks or exclamation marks
    (r"[？?]{3,}|[！!]{3,}",
     "frustration_signal", 0.30),
]

# -- False positive filters ----------------------------------------------------

# Quote character set: curly double+single + CJK corner brackets + ASCII " and '
_Q = r'“”‘’「」『』"\''

FALSE_POSITIVE_FILTERS = [
    # Code blocks
    r"^\s{4,}(?:def |class |import |from |if |else|elif |return |print|#|//|/\*)",

    # Citation / quote markers (10+ chars between any matching quotes)
    r"[" + _Q + r"][^" + _Q + r"]{10,}[" + _Q + r"]",
    r"(?:cite|引用|摘自|来源|参考文献|according to)",

    # Hypothetical / conditional
    r"(?:如果|假设|假如|要是|万一|即使).*(?:不是|不对|错了)",

    # Meta-discussion about errors
    r"(?:如何检测|怎么判断|如何识别).*(?:错误|不对|问题)",

    # Plain negation about code/algorithms/papers (not Claude)
    r"(?:这段代码|这个函数|这个算法|该论文|该作者|该研究).*(?:不是|不对)",

    # User correcting themselves
    r"(?:我刚[才刚]说错了|我之前说错了|我搞错了|我弄错了|我理解错了)",
]

# Pre-compiled
_FILTER_RES = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in FALSE_POSITIVE_FILTERS]

# -- Sensitive content filter ---------------------------------------------------

SENSITIVE_PATTERNS = [
    r'(?:api[_-]?key|apikey|secret|token|password|passwd|credential)\s*[:=]\s*\S+',
    r'(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{10,}',
    r'minta_[A-Za-z0-9]{30,}',
    r'(?:C:|D:|E:)\\(?:Users|用户)\\[^\\]{3,}',
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    r'1[3-9]\d{9}',
]

_SENSITIVE_RES = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]


def _redact_sensitive(text: str) -> str:
    """Replace sensitive content with placeholder markers."""
    for pattern in _SENSITIVE_RES:
        text = pattern.sub("[REDACTED]", text)
    return text


# -- Candidate ID generation ----------------------------------------------------

def _make_candidate_id(user_excerpt: str, session_id: str) -> str:
    """Generate a stable, content-based candidate ID for deduplication."""
    normalized = re.sub(r'\s+', '', user_excerpt.strip().lower())[:200]
    seed = f"{normalized}|{session_id}"
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


# -- False positive check -------------------------------------------------------

def _is_false_positive(text: str, excerpt: str) -> bool:
    """Check if the detected signal is likely a false positive.

    Returns True if the match should be suppressed.
    """
    for pattern in _FILTER_RES:
        if pattern.search(text):
            return True

    if len(excerpt.strip()) < 6:
        return True

    if excerpt.strip() in ("不是", "不对", "错了", "不行"):
        return True

    return False


# -- Core detection -------------------------------------------------------------

def detect_correction_candidate(user_prompt: str, session_id: str = "") -> Optional[dict]:
    """Scan user prompt for correction signals. Returns a CANDIDATE dict or None.

    This is intentionally conservative -- it only flags clear correction signals,
    not every negation or disagreement.
    """
    if not user_prompt or len(user_prompt) < 4:
        return None

    if not _config.get("enabled", True):
        return None

    signals = []
    for pattern, sig_type, boost in CORRECTION_PATTERNS:
        for m in re.finditer(pattern, user_prompt, re.IGNORECASE):
            start = max(0, m.start() - 60)
            end = min(len(user_prompt), m.end() + 140)
            excerpt = user_prompt[start:end].strip()

            if _is_false_positive(user_prompt, excerpt):
                continue

            confidence = min(0.85, 0.60 + boost)
            signals.append({
                "signal_type": sig_type,
                "matched": m.group(),
                "excerpt": excerpt[:300],
                "confidence": round(confidence, 2),
            })

    if not signals:
        return None

    signals.sort(key=lambda s: s["confidence"], reverse=True)
    signals = signals[:2]

    best = signals[0]
    candidate_id = _make_candidate_id(best["excerpt"], session_id)

    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "user_prompt_submit",
        "status": "CANDIDATE",
        "signal_types": [s["signal_type"] for s in signals],
        "user_excerpt": _redact_sensitive(best["excerpt"]),
        "matched_trigger": best["matched"],
        "all_signals": [
            {"type": s["signal_type"], "confidence": s["confidence"], "matched": s["matched"]}
            for s in signals
        ],
        "prior_assistant_context_ref": None,
        "proposed_correction": None,
        "confidence": best["confidence"],
        "requires_review": True,
    }


# -- Enqueue --------------------------------------------------------------------

def _post_to_server(candidate: dict) -> bool:
    """Try to POST candidate to the Minta server (8772 MySQL inbox).

    Uses X-API-Key auth. Falls back to counter_server (18720) if 8772 is down.
    Returns True on success.
    """
    api_key = _config.get("api_key", "")
    endpoint = _config.get("endpoint", "")
    fallback_endpoint = _config.get("fallback_endpoint", "")
    timeout_ms = _config.get("timeout_ms", 300)
    timeout_sec = max(0.1, timeout_ms / 1000.0)

    text = candidate.get("user_excerpt", "")
    confidence = candidate.get("confidence", 0.75)
    tags = candidate.get("signal_types", [])

    # Try primary (8772 MySQL inbox) with API key
    if endpoint and api_key:
        try:
            import urllib.parse
            params = urllib.parse.urlencode({
                "text": text,
                "confidence": confidence,
            })
            url = f"{endpoint}?{params}"
            body = json.dumps(tags, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-API-Key": api_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass  # fall through to fallback

    # Try fallback (18720 counter_server)
    if fallback_endpoint:
        try:
            body = json.dumps(candidate, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                fallback_endpoint,
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                return resp.status == 200
        except Exception:
            return False

    return False


def _append_local_spool(candidate: dict) -> None:
    """Write candidate to local JSONL fallback queue."""
    queue_path = _config.get("fallback_queue", "")
    if not queue_path:
        return
    try:
        p = Path(queue_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _is_duplicate(candidate_id: str) -> bool:
    """Check if a candidate with this ID already exists in the local queue."""
    queue_path = _config.get("fallback_queue", "")
    if not queue_path:
        return False
    try:
        p = Path(queue_path)
        if not p.exists():
            return False
        lines = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                lines.append(line)
        recent = lines[-200:]
        for line in recent:
            try:
                entry = json.loads(line.strip())
                if entry.get("candidate_id") == candidate_id:
                    return True
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return False


def enqueue_candidate(candidate: dict) -> bool:
    """Enqueue a candidate: try HTTP POST, fall back to local JSONL.

    Returns True if the candidate was successfully enqueued (either path).
    """
    if _is_duplicate(candidate.get("candidate_id", "")):
        return False

    if _post_to_server(candidate):
        return True

    _append_local_spool(candidate)
    return True


def try_capture(user_prompt: str, session_id: str = "") -> Optional[dict]:
    """Main entry point: detect -> build -> enqueue. Returns candidate or None.

    Call this from user_prompt_submit hook. It will never raise.
    """
    try:
        candidate = detect_correction_candidate(user_prompt, session_id)
        if candidate is None:
            return None

        enqueue_candidate(candidate)
        return candidate
    except Exception:
        return None
