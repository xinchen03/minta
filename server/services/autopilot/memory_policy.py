"""Memory Policy Engine — deterministic rule-based decision maker.
Pure functions, no side effects, no DB access, no external API calls."""
import re
from typing import Any, Dict, List, Optional

from services.autopilot.schemas import (
    PolicyInput,
    PolicyResult,
    Decision,
    MemoryType,
    Scope,
    UpdateOperation,
)

# ── Trigger patterns (deterministic, no LLM) ──

READ_TRIGGERS = [
    r"继续",
    r"上次",
    r"之前",
    r"按之前",
    r"还记得",
    r"这个项目",
    r"规则",
    r"约束",
    r"我的偏好",
    r"我的习惯",
    r"上下文",
]

WRITE_TRIGGERS = [
    r"记住",
    r"以后",
    r"默认",
    r"我的偏好",
    r"这个项目用",
    r"这个项目不要",
    r"规则是",
    r"我应该",
    r"以后都",
    r"总是",
    r"习惯",
]

COUNTER_TRIGGERS = [
    r"不是",
    r"错了",
    r"不对",
    r"你理解错了",
    r"不是全局",
    r"只是这个项目",
    r"例外",
    r"不适用",
    r"搞错了",
    r"不行",
]

UPDATE_TRIGGERS = [
    r"改成",
    r"更新为",
    r"替换",
    r"作废",
    r"废弃",
    r"不要再用",
    r"现在改为",
    r"不再",
    r"重新考虑",
]

# ── Pure helpers ──


def match_any(text, patterns):
    # type: (str, List[str]) -> List[str]
    """Return all patterns that match the text."""
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def decide_policy(inp):
    # type: (PolicyInput) -> PolicyResult
    """Main entry: route to pre_turn or post_turn policy."""
    if inp.phase == "pre_turn":
        return decide_pre_turn(inp)
    if inp.phase == "post_turn":
        return decide_post_turn(inp)
    raise ValueError("Unsupported phase: %s" % inp.phase)


def decide_pre_turn(inp):
    # type: (PolicyInput) -> PolicyResult
    """Read policy: should we recall memory before answering?"""
    user_text = inp.user_message or ""
    matches = match_any(user_text, READ_TRIGGERS)

    project_signal = bool(inp.project_id) or bool(
        re.search(r"项目|repo|代码库|系统|产品|Minta|BriefBuilder", user_text, re.I)
    )

    should_read = bool(matches) or project_signal

    confidence = 0.0
    payload = None
    reason = ""

    if should_read:
        confidence = min(0.95, 0.55 + 0.08 * len(matches) + (0.15 if project_signal else 0))
        reason = "Detected prior-context or project-context signals"
        if matches:
            reason += ": %s" % matches[0]
        payload = {"queries": build_read_queries(user_text, inp.project_id)}

    return PolicyResult(
        phase="pre_turn",
        read=Decision(
            should_run=should_read,
            confidence=round(confidence, 2),
            reason=reason,
            payload=payload,
        ),
        write=Decision(False),
        counter_capture=Decision(False),
        update=Decision(False),
    )


def decide_post_turn(inp):
    # type: (PolicyInput) -> PolicyResult
    """Write/Counter/Update policy: should we capture after answering?"""
    user_text = inp.user_message or ""
    assistant_text = inp.assistant_response or ""
    combined = "%s\n%s" % (user_text, assistant_text)

    write_matches = match_any(combined, WRITE_TRIGGERS)
    counter_matches = match_any(combined, COUNTER_TRIGGERS)
    update_matches = match_any(combined, UPDATE_TRIGGERS)

    should_write = bool(write_matches)
    should_counter = bool(counter_matches)
    should_update = bool(update_matches) or (
        "不是全局" in combined and "项目" in combined
    )

    write_payload = None
    counter_payload = None
    update_payload = None

    if should_write:
        write_payload = {
            "items": [
                {
                    "type": infer_memory_type(combined),
                    "scope": infer_scope(combined, inp.project_id),
                    "content": extract_candidate_memory(combined),
                    "route": "inbox",
                }
            ]
        }

    if should_counter:
        counter_payload = {
            "items": [
                {
                    "scope": infer_scope(combined, inp.project_id),
                    "counterexample": extract_counterexample(combined),
                    "route": "counter_inbox",
                }
            ]
        }

    if should_update:
        update_payload = {
            "operation": infer_update_operation(combined),
            "scope": infer_scope(combined, inp.project_id),
            "route": "review",
        }

    return PolicyResult(
        phase="post_turn",
        read=Decision(False),
        write=Decision(
            should_run=should_write,
            confidence=round(min(0.92, 0.55 + 0.1 * len(write_matches)), 2)
            if should_write
            else 0.0,
            reason="Detected durable memory signal" if should_write else "",
            payload=write_payload,
        ),
        counter_capture=Decision(
            should_run=should_counter,
            confidence=round(min(0.95, 0.65 + 0.1 * len(counter_matches)), 2)
            if should_counter
            else 0.0,
            reason="Detected correction or counterexample signal"
            if should_counter
            else "",
            payload=counter_payload,
        ),
        update=Decision(
            should_run=should_update,
            confidence=round(min(0.90, 0.60 + 0.1 * len(update_matches)), 2)
            if should_update
            else 0.0,
            reason="Detected update or scoped exception signal"
            if should_update
            else "",
            payload=update_payload,
        ),
    )


# ── Utility functions ──


def build_read_queries(user_text, project_id=None):
    # type: (str, Optional[str]) -> List[Dict[str, str]]
    """Build structured read queries from user message."""
    base = user_text[:160]

    queries = [
        {"type": "user_preferences",
         "query": "用户偏好 规则 约束 %s" % base},
        {"type": "project_context",
         "query": "项目上下文 决策 历史方案 %s" % base},
        {"type": "counterexamples",
         "query": "反例 例外 失败案例 限制 %s" % base},
    ]

    if project_id:
        for q in queries:
            q["project_id"] = project_id

    return queries


def infer_memory_type(text):
    # type: (str) -> str
    """Infer what type of memory should be created."""
    if re.search(r"偏好|喜欢|不喜欢|默认", text):
        return "user_preference"
    if re.search(r"项目|repo|代码库|系统", text):
        return "project_constraint"
    if re.search(r"规则|必须|不要|总是|禁止", text):
        return "rule"
    if re.search(r"失败|踩坑|不适用|例外", text):
        return "counterexample"
    return "context_note"


def infer_scope(text, project_id=None):
    # type: (str, Optional[str]) -> str
    """Infer whether this memory is global or project-scoped."""
    if re.search(r"这个项目|当前项目|本项目|只是这个项目|不是全局", text):
        if project_id:
            return "project:%s" % project_id
        return "project:current"

    if re.search(r"全局|以后都|默认|总是|所有项目", text):
        return "global:user"

    if project_id:
        return "project:%s" % project_id

    return "unknown"


def extract_candidate_memory(text):
    # type: (str) -> str
    """Extract the portion of text that should be stored as memory."""
    return text[-500:].strip()


def extract_counterexample(text):
    # type: (str) -> str
    """Extract the portion of text that contains the counterexample."""
    return text[-500:].strip()


def infer_update_operation(text):
    # type: (str) -> str
    """Determine what kind of update operation is needed."""
    if re.search(r"不是全局|只是这个项目|例外|不适用", text):
        return "add_exception"
    if re.search(r"改成|更新为|替换|现在改为", text):
        return "replace_review"
    if re.search(r"作废|废弃|不要再用|不再", text):
        return "invalidate_review"
    return "review"
