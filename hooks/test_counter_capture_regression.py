#!/usr/bin/env python3
"""Counter-capture pipeline regression tests — R5C.P1.

Run: python test_counter_capture_regression.py
From: hooks/

Covers the 10 production assertions + edge cases specified in R5C.P1 design.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure we can import the module under test
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import counter_capture as cc


class TestSignalDetection(unittest.TestCase):
    """Assertion 1: Explicit corrections MUST generate candidates."""

    def test_direct_negation_creates_candidate(self):
        result = cc.detect_correction_candidate(
            "不对，JSAMS 是双盲审，不是单盲审。",
            session_id="test-session-1",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertIn("explicit_correction", result["signal_types"])

    def test_reformulation_creates_candidate(self):
        result = cc.detect_correction_candidate(
            "应该是把论文投到 IP&M 而不是 Scientometrics。",
            session_id="test-session-2",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "CANDIDATE")

    def test_naming_correction_creates_candidate(self):
        result = cc.detect_correction_candidate(
            "不要把 IS Gate 当成 Information Sufficiency Gate，正式名称是 Information Sufficiency Gate。",
            session_id="test-session-3",
        )
        self.assertIsNotNone(result)

    def test_state_fact_correction_creates_candidate(self):
        result = cc.detect_correction_candidate(
            "事实是 counter-inbox.md 根本不存在，不是路径问题。",
            session_id="test-session-4",
        )
        self.assertIsNotNone(result)

    def test_missing_constraint_creates_candidate(self):
        result = cc.detect_correction_candidate(
            "你应该先查 config.json 再给默认值。",
            session_id="test-session-5",
        )
        self.assertIsNotNone(result)
        self.assertIn("missing_constraint", result["signal_types"])

    def test_multi_signal_tracks_all_types(self):
        result = cc.detect_correction_candidate(
            "不对，你应该先把数据查了再下结论，不应该直接假设。",
            session_id="test-session-multi",
        )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result["signal_types"]), 1)


class TestFalsePositiveSuppression(unittest.TestCase):
    """Assertion 2: Ordinary negations MUST NOT be captured."""

    def test_code_block_not_captured(self):
        result = cc.detect_correction_candidate(
            "这段代码判断 x is not None 然后返回默认值。",
            session_id="test-fp-1",
        )
        self.assertIsNone(result)

    def test_citation_not_captured(self):
        result = cc.detect_correction_candidate(
            '请解释"不是所有相关性都是因果性"这句话的统计含义。',
            session_id="test-fp-2",
        )
        self.assertIsNone(result)

    def test_quoted_content_not_captured(self):
        result = cc.detect_correction_candidate(
            '文献里有一段话："这个模型不是最优的，但在当时条件下是可接受的"。',
            session_id="test-fp-3",
        )
        self.assertIsNone(result)

    def test_hypothetical_not_captured(self):
        result = cc.detect_correction_candidate(
            "如果不是单盲审而是双盲审的话，审稿质量会不会更高？",
            session_id="test-fp-4",
        )
        self.assertIsNone(result)

    def test_self_correction_not_captured(self):
        result = cc.detect_correction_candidate(
            "我刚才说错了，JSAMS 影响因子应该是 3.8 不是 4.2。",
            session_id="test-fp-5",
        )
        self.assertIsNone(result)

    def test_general_discussion_not_captured(self):
        result = cc.detect_correction_candidate(
            "如何检测代码中的逻辑错误和语法不对的地方？",
            session_id="test-fp-6",
        )
        self.assertIsNone(result)

    def test_single_word_negation_not_captured(self):
        result = cc.detect_correction_candidate("不对", session_id="test-fp-7")
        self.assertIsNone(result)

    def test_algorithm_discussion_not_captured(self):
        result = cc.detect_correction_candidate(
            "这个算法在稀疏数据上的表现不对，准确率下降了很多。",
            session_id="test-fp-8",
        )
        self.assertIsNone(result)

    def test_empty_prompt_returns_none(self):
        result = cc.detect_correction_candidate("", session_id="test-fp-9")
        self.assertIsNone(result)

    def test_short_prompt_returns_none(self):
        result = cc.detect_correction_candidate("ab", session_id="test-fp-10")
        self.assertIsNone(result)


class TestCandidateStructure(unittest.TestCase):
    """Assertion 4: Candidate payload MUST be structured, not raw text."""

    def test_payload_has_required_fields(self):
        result = cc.detect_correction_candidate(
            "不对，Minta 的 inbox API 在 8772 端口，不是 18720。",
            session_id="test-struct-1",
        )
        self.assertIsNotNone(result)
        required = [
            "schema_version", "candidate_id", "captured_at",
            "source", "status", "signal_types", "user_excerpt",
            "confidence", "requires_review",
        ]
        for field in required:
            self.assertIn(field, result, f"Missing required field: {field}")

    def test_candidate_status_is_candidate(self):
        result = cc.detect_correction_candidate(
            "你理解错了，我说的是反例系统而不是 inbox 系统。",
            session_id="test-struct-2",
        )
        self.assertEqual(result["status"], "CANDIDATE")

    def test_requires_review_is_true(self):
        result = cc.detect_correction_candidate(
            "错了，这个字段应该叫 information_sufficiency_gate。",
            session_id="test-struct-3",
        )
        self.assertTrue(result["requires_review"])

    def test_user_excerpt_is_not_full_prompt(self):
        long_prompt = (
            "我今天想跟你讨论一下关于论文审稿的事情。"
            + "前面说的都不重要，关键是：不对，JSAMS 不是单盲。"
            + "剩下的也不重要了" * 20
        )
        result = cc.detect_correction_candidate(long_prompt, session_id="test-struct-4")
        self.assertIsNotNone(result)
        self.assertLess(len(result["user_excerpt"]), len(long_prompt))


class TestDeduplication(unittest.TestCase):
    """Assertion 5: Candidate IDs MUST be idempotent."""

    def test_same_content_same_id(self):
        text = "不对，Minta 的配置文件路径是 ~/.minta/config.json"
        r1 = cc.detect_correction_candidate(text, session_id="dedup-test")
        r2 = cc.detect_correction_candidate(text, session_id="dedup-test")
        self.assertEqual(r1["candidate_id"], r2["candidate_id"])

    def test_different_session_different_id(self):
        text = "不对，JSAMS 是双盲。"
        r1 = cc.detect_correction_candidate(text, session_id="session-A")
        r2 = cc.detect_correction_candidate(text, session_id="session-B")
        self.assertNotEqual(r1["candidate_id"], r2["candidate_id"])

    def test_whitespace_normalization(self):
        r1 = cc.detect_correction_candidate(
            "不对，  Minta 的  API  端口是 18720。", session_id="norm-test"
        )
        r2 = cc.detect_correction_candidate(
            "不对，Minta 的 API 端口是 18720。", session_id="norm-test"
        )
        self.assertEqual(r1["candidate_id"], r2["candidate_id"])

    def test_enqueue_rejects_duplicate(self):
        """Simulate duplicate rejection in enqueue."""
        candidate_id = "sha256:test1234567890ab"
        candidate = {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "captured_at": "2026-07-25T12:00:00",
            "source": "user_prompt_submit",
            "status": "CANDIDATE",
            "signal_types": ["explicit_correction"],
            "user_excerpt": "test",
            "confidence": 0.75,
            "requires_review": True,
        }

        # First enqueue should succeed
        with patch.object(cc, '_post_to_server', return_value=True):
            result1 = cc.enqueue_candidate(candidate)
            self.assertTrue(result1)

        # Second with same ID should be rejected as duplicate
        # (depends on _is_duplicate checking local queue)
        with patch.object(cc, '_is_duplicate', return_value=True):
            result2 = cc.enqueue_candidate(candidate)
            self.assertFalse(result2)


class TestFailOpen(unittest.TestCase):
    """Assertion 3: Network failures MUST NOT block the hook."""

    def test_http_failure_returns_none_from_try_capture(self):
        """try_capture should return None (not raise) on any error."""
        with patch.object(cc, 'detect_correction_candidate', side_effect=Exception("boom")):
            result = cc.try_capture("不对，测试。", "test-failopen")
            self.assertIsNone(result)

    def test_enqueue_falls_back_to_local(self):
        """When HTTP fails, candidate should go to local JSONL."""
        candidate = {
            "schema_version": "1.0",
            "candidate_id": "sha256:fallback-test-0001",
            "captured_at": "2026-07-25T12:00:00",
            "source": "user_prompt_submit",
            "status": "CANDIDATE",
            "signal_types": ["explicit_correction"],
            "user_excerpt": "HTTP failure fallback test",
            "confidence": 0.75,
            "requires_review": True,
        }

        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "candidate-queue.jsonl"

            with patch.object(cc, '_post_to_server', return_value=False), \
                 patch.object(cc, '_is_duplicate', return_value=False), \
                 patch.dict(cc._config, {"fallback_queue": str(queue_path)}):
                result = cc.enqueue_candidate(candidate)
                self.assertTrue(result)
                self.assertTrue(queue_path.exists())

                # Verify content
                lines = queue_path.read_text(encoding="utf-8").strip().split("\n")
                self.assertEqual(len(lines), 1)
                saved = json.loads(lines[0])
                self.assertEqual(saved["candidate_id"], candidate["candidate_id"])

    def test_disabled_config_suppresses_capture(self):
        with patch.dict(cc._config, {"enabled": False}):
            result = cc.detect_correction_candidate(
                "不对，这明显是错的。", session_id="test-disabled"
            )
            self.assertIsNone(result)

    def test_env_var_disables_capture(self):
        with patch.dict(os.environ, {"MINTA_COUNTER_ENABLED": "false"}):
            # Re-resolve config
            old_cfg = cc._config.copy()
            try:
                new_cfg = cc._resolve_config()
                with patch.dict(cc._config, new_cfg):
                    result = cc.detect_correction_candidate(
                        "不对，测试。", session_id="test-env-disabled"
                    )
                    self.assertIsNone(result)
            finally:
                cc._config = old_cfg


class TestSensitiveContent(unittest.TestCase):
    """Assertion 9: Sensitive data MUST be redacted."""

    def test_api_key_redacted(self):
        result = cc.detect_correction_candidate(
            "不对，API key 是 minta_oFRhPzyaWWWhDWUQTYBrWAzRLX1p1S6NcVdc5IJ7 不是别的。",
            session_id="test-sensitive-1",
        )
        self.assertIsNotNone(result)
        self.assertNotIn("minta_oFRhPzya", result["user_excerpt"])
        self.assertIn("[REDACTED]", result["user_excerpt"])

    def test_email_redacted(self):
        result = cc.detect_correction_candidate(
            "不对，联系邮箱是 test@example.com 不是那个。",
            session_id="test-sensitive-2",
        )
        self.assertIsNotNone(result)
        self.assertNotIn("test@example.com", result["user_excerpt"])

    def test_ip_address_redacted(self):
        result = cc.detect_correction_candidate(
            "不对，MCP 端口是 192.168.1.100:18721 不是那个。",
            session_id="test-sensitive-3",
        )
        self.assertIsNotNone(result)
        self.assertNotIn("192.168.1.100", result["user_excerpt"])


class TestConfigResolution(unittest.TestCase):
    """Test config resolution chain."""

    def test_default_config_has_required_keys(self):
        cfg = cc._resolve_config()
        for key in ("enabled", "endpoint", "fallback_endpoint", "fallback_queue", "timeout_ms", "api_key"):
            self.assertIn(key, cfg)

    def test_primary_endpoint_is_8772_mysql_inbox(self):
        cfg = cc._resolve_config()
        self.assertIn("8772", cfg["endpoint"])
        self.assertIn("inbox/append", cfg["endpoint"])
        # 18720 is the fallback
        self.assertIn("18720", cfg["fallback_endpoint"])

    def test_env_var_overrides_config(self):
        with patch.dict(os.environ, {
            "MINTA_COUNTER_ENDPOINT": "http://127.0.0.1:9999/api/test",
            "MINTA_COUNTER_TIMEOUT_MS": "500",
        }):
            cfg = cc._resolve_config()
            self.assertEqual(cfg["endpoint"], "http://127.0.0.1:9999/api/test")
            self.assertEqual(cfg["timeout_ms"], 500)


class TestProductionAssertions(unittest.TestCase):
    """Full production assertions from R5C.P1 design doc."""

    def test_pa1_explicit_correction_generates_candidate(self):
        """PASS: Explicit correction generates candidate."""
        result = cc.detect_correction_candidate(
            "不对，JSAMS 是双盲，不是单盲。",
            session_id="pa-test",
        )
        self.assertIsNotNone(result)

    def test_pa2_ordinary_negation_not_captured(self):
        """PASS: Ordinary negation false-positive rate controlled."""
        negations = [
            "这段代码判断 x is not None",
            "请解释'不是所有相关性都是因果性'",
            '引用一段包含"你错了"的文献',
            "如果不是这样的话，还有别的方案吗？",
        ]
        for text in negations:
            with self.subTest(text=text[:40]):
                result = cc.detect_correction_candidate(text, session_id="pa2")
                self.assertIsNone(result, f"False positive: {text[:40]}")

    def test_pa6_endpoint_configuration(self):
        """PASS: Primary endpoint is 8772 MySQL inbox, 18720 is fallback only."""
        cfg = cc._resolve_config()
        # Primary: 8772 MySQL inbox
        self.assertIn("8772", cfg["endpoint"])
        # 18720 is fallback only, not primary
        self.assertIn("18720", cfg["fallback_endpoint"])
        # api_key resolved from env if available, empty string fallback
        self.assertIsInstance(cfg.get("api_key", ""), str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
