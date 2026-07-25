#!/usr/bin/env python3
"""UserPromptSubmit hook — stage detection + counter-capture + expert injection.

Reads the user's prompt, detects research stage, captures correction
candidates (R5C.P1 counterexample capture pipeline), and injects context.
Does NOT: block user input, duplicate SessionStart Context Pack.
Exit: always exit 0 (non-blocking advisory hook).
"""
import json, os, re, sys
from pathlib import Path

# ── Counter-capture (R5C.P1) ──────────────────────────────────────────────
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from counter_capture import try_capture as _try_counter_capture
except ImportError:
    _try_counter_capture = None  # graceful degradation if module is missing

STAGE_PATTERNS = [
    (r"选题|idea|研究方向|做什么|research direction|topic", "intake"),
    (r"storm|多视角|矛盾|perspective|大纲|outline|prewriting", "prewriting"),
    (r"文献综述|检索|systematic review|literature|搜索|search|证据|evidence", "evidence_collection"),
    (r"统计|模型|回归|中介|调节|因果|analysis|数据分析|实验", "analysis"),
    (r"综合|synthesis|整合|矛盾|contradiction", "synthesis"),
    (r"写作|撰写|润色|manuscript|论文段落|abstract|introduction|discussion|draft", "writing"),
    (r"核验|事实核查|citation audit|引用核验|复现|reproduc|verify|verification", "verification"),
    (r"审稿|同行评审|reviewer|peer review|review", "peer_review"),
    (r"修回|revision|response|回复|修改", "revision"),
]


def read_stdin():
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def detect_stage(prompt: str) -> str:
    for pattern, stage in STAGE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return stage
    return ""


def main():
    payload = read_stdin()
    if not payload:
        return
    prompt = str(payload.get("prompt", ""))
    if len(prompt) < 10:
        return

    # ── R5C.P1: Counter-capture candidate detection ──
    session_id = str(payload.get("session_id", ""))
    if _try_counter_capture is not None:
        try:
            _try_counter_capture(prompt, session_id)
        except Exception:
            pass  # fail-open: counter capture never blocks the hook

    stage = detect_stage(prompt)
    additions = []
    if stage:
        additions.append(f"Research stage detected: {stage}.")
    if not additions:
        return

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(additions),
        }
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Research] user_prompt_submit error: {e}", file=sys.stderr)
    sys.exit(0)
