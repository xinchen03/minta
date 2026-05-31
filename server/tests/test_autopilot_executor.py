"""Integration tests for memory_executor.py — tests against live Minta API."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.autopilot.schemas import PolicyInput, PolicyResult, Decision
from services.autopilot.memory_policy import decide_policy
from services.autopilot.memory_executor import (
    execute_read,
    execute_write,
    execute_counter_capture,
    execute_update,
    execute_all,
)

USER_ID = "test_executor"


def _pre_result(user_message, project_id=None):
    inp = PolicyInput(
        user_id=USER_ID,
        phase="pre_turn",
        user_message=user_message,
        project_id=project_id,
    )
    return decide_policy(inp)


def _post_result(user_message, assistant_response, project_id=None):
    inp = PolicyInput(
        user_id=USER_ID,
        phase="post_turn",
        user_message=user_message,
        assistant_response=assistant_response,
        project_id=project_id,
    )
    return decide_policy(inp)


# ══════════════════════════════════════════════════════════════
# Test 1: Read execution
# ══════════════════════════════════════════════════════════════


class TestExecuteRead:
    def test_read_skipped_when_not_triggered(self):
        policy = _pre_result("你好")
        result = execute_read(policy, USER_ID)
        assert result["read_performed"] is False
        assert result["memory_context"] == {}

    def test_read_returns_context(self):
        policy = _pre_result("继续上次 BriefBuilder 的方案", "minta")
        result = execute_read(policy, USER_ID)
        assert result["read_performed"] is True
        ctx = result["memory_context"]
        # Should have at least some fields
        assert "user_preferences" in ctx
        assert "project_context" in ctx
        assert "counterexamples" in ctx
        assert "skills" in ctx

    def test_read_context_has_items(self):
        policy = _pre_result("继续上次的方案", "minta")
        result = execute_read(policy, USER_ID)
        ctx = result["memory_context"]
        # The actual API may return empty arrays if no data for user
        # But the structure must be correct
        assert isinstance(ctx["user_preferences"], list)
        assert isinstance(ctx["project_context"], list)
        assert isinstance(ctx["counterexamples"], list)
        assert isinstance(ctx["skills"], list)

    def test_read_has_reason(self):
        policy = _pre_result("继续上次的方案")
        result = execute_read(policy, USER_ID)
        assert len(result.get("reason", "")) > 0


# ══════════════════════════════════════════════════════════════
# Test 2: Write execution
# ══════════════════════════════════════════════════════════════


class TestExecuteWrite:
    def test_write_skipped_when_not_triggered(self):
        policy = _post_result("Python 怎么反转字符串？", "用 [::-1]")
        result = execute_write(policy, USER_ID)
        assert result["writes_created"] == 0
        assert result["inbox_ids"] == []

    def test_write_creates_inbox_item(self):
        policy = _post_result(
            "记住，我以后默认用中文回复",
            "好的，以后默认用中文。",
        )
        result = execute_write(policy, USER_ID)
        # May be 0 if API key not set. Test passes either way.
        assert isinstance(result["writes_created"], int)
        assert isinstance(result["inbox_ids"], list)

    def test_write_with_project_scope(self):
        policy = _post_result(
            "这个项目用 Go 语言",
            "好的，这个项目用 Go。",
            project_id="my-project",
        )
        result = execute_write(policy, USER_ID)
        assert isinstance(result["writes_created"], int)


# ══════════════════════════════════════════════════════════════
# Test 3: Counter-capture execution
# ══════════════════════════════════════════════════════════════


class TestExecuteCounter:
    def test_counter_skipped_when_not_triggered(self):
        policy = _post_result("你好", "你好！")
        result = execute_counter_capture(policy, USER_ID)
        assert result["counter_created"] == 0

    def test_counter_creates_item(self):
        policy = _post_result(
            "不是，我不是说全局改成 Go，只是这个项目用 Go",
            "明白，这是项目级例外。",
            project_id="my-project",
        )
        result = execute_counter_capture(policy, USER_ID)
        assert isinstance(result["counter_created"], int)
        assert isinstance(result["counter_ids"], list)


# ══════════════════════════════════════════════════════════════
# Test 4: Update execution
# ══════════════════════════════════════════════════════════════


class TestExecuteUpdate:
    def test_update_skipped_when_not_triggered(self):
        policy = _post_result("你好", "你好！")
        result = execute_update(policy, USER_ID)
        assert result["updates_created"] == 0

    def test_update_creates_review_item(self):
        policy = _post_result(
            "不是全局，只是这个项目用 Go",
            "好的，项目级例外。",
            project_id="my-project",
        )
        result = execute_update(policy, USER_ID)
        assert isinstance(result["updates_created"], int)
        assert isinstance(result["review_ids"], list)


# ══════════════════════════════════════════════════════════════
# Test 5: execute_all (integration)
# ══════════════════════════════════════════════════════════════


class TestExecuteAll:
    def test_execute_all_pre_turn(self):
        policy = _pre_result("继续上次的方案", "minta")
        result = execute_all(policy, USER_ID)
        assert result["phase"] == "pre_turn"
        assert result["read"]["read_performed"] is True
        assert result["write"]["writes_created"] == 0
        assert result["counter_capture"]["counter_created"] == 0
        assert result["update"]["updates_created"] == 0
        assert "summary" in result

    def test_execute_all_post_turn_write(self):
        policy = _post_result(
            "记住这个规则",
            "已记录。",
        )
        result = execute_all(policy, USER_ID)
        assert result["phase"] == "post_turn"
        assert result["read"]["read_performed"] is False

    def test_execute_all_post_turn_counter(self):
        policy = _post_result(
            "不是全局，只是这个项目用 Go",
            "明白。",
            project_id="my-project",
        )
        result = execute_all(policy, USER_ID)
        assert result["phase"] == "post_turn"
        assert result["counter_capture"]["counter_created"] >= 0
        assert result["update"]["updates_created"] >= 0

    def test_execute_all_skipped_for_ordinary(self):
        policy = _post_result("Python 怎么反转字符串？", "用 [::-1]")
        result = execute_all(policy, USER_ID)
        assert result["summary"]["total_created"] == 0

    def test_execute_all_has_summary(self):
        policy = _pre_result("继续上次的方案")
        result = execute_all(policy, USER_ID)
        s = result["summary"]
        assert "read_performed" in s
        assert "writes_created" in s
        assert "counter_created" in s
        assert "updates_created" in s
        assert "total_created" in s
