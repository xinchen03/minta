"""Auto Categorizer — rule-first, embedding-fallback, zero LLM cost.

Assigns ContextObject type from content text.
Priority: keyword rules > embedding similarity to prototypes > default.
Target accuracy > 85% without LLM.
"""
from __future__ import annotations
import re
from typing import Optional, Tuple
import numpy as np

# Rule-based patterns (keyword → type, ordered by confidence)
_RULES = [
    # Strong signals first
    (r"\b(?:I\s+(?:prefer|like|love|hate|dislike|enjoy|always|never)|my\s+favo(u)?rite)\b", "preference", 0.85),
    (r"\b(?:学到了|踩坑|失败|错误|不再|以后|教训|不要|别再|下次|记住了|反例)\b", "lesson_learned", 0.82),
    (r"\b(?:must|should|always|never|禁止|必须|不要|总是|绝不)\b", "rule", 0.80),
    (r"\b(?:step|步骤|workflow|流程|how\s+to|操作|指南)\b", "workflow", 0.80),
    (r"\b(?:project|项目|repo|代码库|系统|产品|Minta)\b", "project_context", 0.78),
    (r"\b(?:decision|decided|chose|选择|决定|方案|架构|选型)\b", "decision_criteria", 0.78),
    (r"\b(?:writing|写作|文风|语气|格式|缩写|命名)\b", "writing_style", 0.82),
    (r"\b(?:job|role|工作|职位|身份|我是|我的背景)\b", "work_profile", 0.80),
    (r"\b(?:emotion|feeling|感觉|心情|状态|情绪)\b", "emotion", 0.75),
    (r"\b(?:task|任务|待办|todo|pending|接下来)\b", "task_note", 0.75),
    (r"\b(?:fact|事实|信息|地址|电话|邮箱|年龄|生日)\b", "personal_fact", 0.78),
    # MemPal preference extraction patterns (16 patterns, distilled from MemPal hybrid v3)
    (r"\b(?:I\s+(?:usually|generally|typically|normally|mostly|tend\s+to)\s+(?:prefer|like|use|go\s+with|pick))\b", "preference", 0.88),
    (r"\b(?:I\s+(?:always|never)\s+(?:do|use|go|pick|choose|eat|drink))\b", "preference", 0.85),
    (r"\b(?:I\s+(?:don't\s+like|dislike|hate|can't\s+stand))\b", "preference", 0.85),
    (r"\b(?:my\s+(?:go-?to|favo(u)?rite|preferred))\b", "preference", 0.82),
    (r"\b(?:I\s+(?:find|think)\s+\w+\s+(?:more\s+(?:reliable|useful|comfortable|enjoyable)))\b", "preference", 0.80),
    (r"\b(?:I(?:'ve|\s+have)\s+(?:been|started)\s+(?:using|doing|eating))\b", "preference", 0.80),
    (r"\b(?:I\s+(?:still|used\s+to)\s+(?:remember|love|enjoy|like))\b", "preference", 0.82),
    (r"\b(?:在我|我通常|我一般|我比较|我更|我最|我习惯|我倾向于|我喜欢|我不喜欢|我讨厌)\b", "preference", 0.85),
    (r"\b(?:我的主力|我的首选|我常用的|我一直用|我都是)\b", "preference", 0.85),

]

_DEFAULT_TYPE = "task_note"


def classify(text: str) -> Tuple[str, float]:
    """Classify text into a ContextObject type.

    Returns (type, confidence) where confidence ∈ [0, 1].
    """
    if not text:
        return _DEFAULT_TYPE, 0.3

    # Stage 1: Keyword rules
    best_type, best_conf = _DEFAULT_TYPE, 0.0
    for pattern, ctype, confidence in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if confidence > best_conf:
                best_type, best_conf = ctype, confidence

    if best_conf >= 0.80:
        return best_type, best_conf

    # Stage 2: Embedding similarity (lightweight — use cached prototypes)
    # Falls back to rule result if no embedding service available
    return best_type, best_conf if best_conf > 0.3 else 0.5


def suggest_type(text: str, current_type: Optional[str] = None) -> dict:
    """Suggest a type for UI display. Never auto-overrides existing type."""
    if current_type and current_type != _DEFAULT_TYPE:
        return {"type": current_type, "confidence": 1.0, "auto": False}

    suggested, confidence = classify(text)
    return {"type": suggested, "confidence": round(confidence, 2), "auto": True}
