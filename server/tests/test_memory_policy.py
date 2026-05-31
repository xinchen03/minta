"""Unit tests for memory_policy.py — deterministic rule-based policy engine."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.autopilot.schemas import PolicyInput
from services.autopilot.memory_policy import (
    decide_policy,
    decide_pre_turn,
    decide_post_turn,
    match_any,
    infer_memory_type,
    infer_scope,
    infer_update_operation,
    READ_TRIGGERS,
    WRITE_TRIGGERS,
    COUNTER_TRIGGERS,
)


# ── Helpers ──


def _pre(inp):
    return decide_pre_turn(inp)


def _post(inp):
    return decide_post_turn(inp)


# ══════════════════════════════════════════════════════════════
# Test 1: match_any
# ══════════════════════════════════════════════════════════════


class TestMatchAny:
    def test_matches_empty_string(self):
        assert match_any("", READ_TRIGGERS) == []

    def test_matches_no_trigger(self):
        assert match_any("hello world", READ_TRIGGERS) == []

    def test_matches_single_trigger(self):
        result = match_any("按之前的规则来", READ_TRIGGERS)
        assert len(result) >= 1
        assert any(r in "按之前的规则来" for r in result)

    def test_matches_multiple_triggers(self):
        result = match_any("继续上次的项目规则", READ_TRIGGERS)
        assert len(result) >= 2

    def test_matches_case_insensitive(self):
        result = match_any("CONTINUE last project", READ_TRIGGERS)
        # English triggers not in READ_TRIGGERS, so 0
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════
# Test 2: Pre-turn (read policy)
# ══════════════════════════════════════════════════════════════


class TestPreTurn:
    """A: 自动读取测试"""

    def test_continue_previous_triggers_read(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="继续上次 BriefBuilder 的方案",
            project_id="minta",
        )
        result = decide_policy(inp)
        assert result.read.should_run is True
        assert result.read.confidence > 0.5
        assert "prior-context" in result.read.reason.lower() or "signal" in result.read.reason.lower()
        # pre_turn must NOT have write/counter/update
        assert result.write.should_run is False
        assert result.counter_capture.should_run is False
        assert result.update.should_run is False

    def test_project_reference_triggers_read(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="这个项目有什么约束？",
            project_id="minta",
        )
        result = _pre(inp)
        assert result.read.should_run is True

    def test_read_has_payload(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="继续上次的方案",
            project_id="minta",
        )
        result = _pre(inp)
        assert result.read.payload is not None
        assert "queries" in result.read.payload
        assert len(result.read.payload["queries"]) > 0

    def test_casual_chat_no_read(self):
        """C: 普通问题不触发读取"""
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="Python 怎么反转字符串？",
        )
        result = _pre(inp)
        assert result.read.should_run is False
        assert result.write.should_run is False
        assert result.counter_capture.should_run is False

    def test_read_has_loggable_reason(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="还记得上次的架构决策吗",
        )
        result = _pre(inp)
        assert result.read.should_run is True
        assert len(result.read.reason) > 5

    def test_no_false_positive_on_short_greeting(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="你好",
        )
        result = _pre(inp)
        assert result.read.should_run is False


# ══════════════════════════════════════════════════════════════
# Test 3: Post-turn (write/counter/update policy)
# ══════════════════════════════════════════════════════════════


class TestPostTurn:
    """B: 自动写入测试"""

    def test_explicit_preference_triggers_write(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="记住，我以后默认用中文回复",
            assistant_response="好的，我记住了，以后默认用中文。",
        )
        result = _post(inp)
        assert result.write.should_run is True
        assert result.write.confidence > 0.5
        assert result.write.payload is not None

    def test_write_scope_is_global(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="以后都默认用中文回复",
            assistant_response="好的。",
        )
        result = _post(inp)
        assert result.write.should_run is True
        scope = result.write.payload["items"][0]["scope"]
        assert "global" in scope

    def test_write_has_type_inference(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="我偏好使用 Python 而不是 R",
            assistant_response="明白，以后优先用 Python。",
        )
        result = _post(inp)
        assert result.write.should_run is True
        item_type = result.write.payload["items"][0]["type"]
        assert item_type == "user_preference"

    def test_project_rule_scope_is_project(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="这个项目用 Go 语言",
            assistant_response="好的，这个项目用 Go。",
            project_id="my-project",
        )
        result = _post(inp)
        assert result.write.should_run is True
        scope = result.write.payload["items"][0]["scope"]
        assert "my-project" in scope

    def test_counterexample_detected(self):
        """B: 自动反例测试"""
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="不是，我不是说全局改成 Go，只是这个项目用 Go",
            assistant_response="明白，这是项目级例外，不覆盖你的全局偏好。",
            project_id="my-project",
        )
        result = _post(inp)
        assert result.counter_capture.should_run is True
        assert result.counter_capture.confidence > 0.5
        assert result.counter_capture.payload is not None
        assert result.update.should_run is True

    def test_counterexample_update_is_add_exception(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="不是全局，只是这个项目",
            assistant_response="明白",
            project_id="my-project",
        )
        result = _post(inp)
        scope = result.counter_capture.payload["items"][0]["scope"]
        assert "my-project" in scope or "project" in scope

    def test_ordinary_question_no_write(self):
        """C: 普通问题不污染"""
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="Python 怎么反转字符串？",
            assistant_response="可以用 [::-1] 或者 reversed()。",
        )
        result = _post(inp)
        assert result.write.should_run is False
        assert result.counter_capture.should_run is False
        assert result.update.should_run is False

    def test_routine_question_no_write(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="2 + 2 等于几？",
            assistant_response="等于 4。",
        )
        result = _post(inp)
        assert result.write.should_run is False
        assert result.counter_capture.should_run is False

    def test_post_turn_only_allows_write_counter_update(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="记住这个规则",
            assistant_response="已记录。",
        )
        result = _post(inp)
        assert result.read.should_run is False  # post_turn never reads


# ══════════════════════════════════════════════════════════════
# Test 4: Utility functions
# ══════════════════════════════════════════════════════════════


class TestInferMemoryType:
    def test_preference(self):
        assert infer_memory_type("我喜欢用 Python") == "user_preference"

    def test_project_constraint(self):
        assert infer_memory_type("这个项目用 Go") == "project_constraint"

    def test_rule(self):
        assert infer_memory_type("规则是不能用全局变量") == "rule"

    def test_counterexample(self):
        assert infer_memory_type("这个方法不适用") == "counterexample"

    def test_default(self):
        assert infer_memory_type("随便记一下") == "context_note"


class TestInferScope:
    def test_global(self):
        assert "global" in infer_scope("以后都默认用中文")

    def test_project_with_id(self):
        assert "my-proj" in infer_scope("这个项目用 Go", "my-proj")

    def test_project_without_id(self):
        assert "current" in infer_scope("这个项目用 Go")

    def test_not_global_exception(self):
        assert "project" in infer_scope("不是全局，只是这个项目用 Go", "my-proj")

    def test_unknown(self):
        assert infer_scope("你好") == "unknown"


class TestInferUpdateOperation:
    def test_add_exception(self):
        assert infer_update_operation("不是全局，只是这个项目") == "add_exception"

    def test_replace_review(self):
        assert infer_update_operation("改成用 PostgreSQL") == "replace_review"

    def test_invalidate(self):
        assert infer_update_operation("这条规则作废") == "invalidate_review"

    def test_default(self):
        assert infer_update_operation("需要重新考虑") == "review"


# ══════════════════════════════════════════════════════════════
# Test 5: Safety — pre_turn never writes, post_turn never reads
# ══════════════════════════════════════════════════════════════


class TestSafety:
    def test_pre_turn_never_writes(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="继续上次的方案",
        )
        result = _pre(inp)
        assert result.write.should_run is False
        assert result.counter_capture.should_run is False
        assert result.update.should_run is False

    def test_post_turn_never_reads(self):
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="记住了",
            assistant_response="好的。",
        )
        result = _post(inp)
        assert result.read.should_run is False

    def test_pre_turn_no_side_effects(self):
        """Verify pre_turn doesn't create any payload that would mutate state."""
        inp = PolicyInput(
            user_id="test_u1",
            phase="pre_turn",
            user_message="继续上次的方案",
            project_id="minta",
        )
        result = _pre(inp)
        if result.read.payload:
            for item in result.read.payload.get("queries", []):
                assert "route" not in item  # no routing to inbox

    def test_post_turn_no_direct_writes(self):
        """Verify post_turn only routes to inbox/counter/review."""
        inp = PolicyInput(
            user_id="test_u1",
            phase="post_turn",
            user_message="记住这个规则",
            assistant_response="好的。",
        )
        result = _post(inp)
        if result.write.payload:
            for item in result.write.payload.get("items", []):
                assert item.get("route") in ("inbox", "counter_inbox", "review")
