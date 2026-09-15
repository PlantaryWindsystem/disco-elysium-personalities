from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_engine import (  # noqa: E402
    CheckError,
    active_thought_audit,
    active_check,
    difficulty_name,
    normalize_dc,
    passive_check,
    parse_situational_modifiers,
)


SKILL = {
    "skill": "逻辑思维",
    "base": 6,
    "thought_modifiers": [{"source": "工具使用研究", "value": 1}],
    "thought_total": 1,
    "effective": 7,
}


class CheckEngineTests(unittest.TestCase):
    def test_active_thought_audit_is_compact_and_only_returns_researching_thoughts(self):
        thoughts = {
            "thoughts": [
                {
                    "id": "earth-tool-study",
                    "name": "工具使用研究",
                    "status": "研究中",
                    "progress": 3,
                    "required_progress": 4,
                    "progress_cues": ["用新的操作记录检查说明是否清楚"],
                    "problem": "很长的问题文本，不应进入日常审计。",
                    "solution": "尚未完成的解答，也不应进入日常审计。",
                    "progress_log": [{"step": 3, "note": "要求概念说明实际效果。"}],
                },
                {
                    "id": "earth-process-review",
                    "name": "流程复核完成",
                    "status": "已内在化",
                    "progress": 4,
                    "required_progress": 4,
                },
            ]
        }

        result = active_thought_audit(thoughts)

        self.assertEqual(result, [{
            "id": "earth-tool-study",
            "name": "工具使用研究",
            "progress": 3,
            "required_progress": 4,
            "progress_cues": ["用新的操作记录检查说明是否清楚"],
            "latest_progress_note": "要求概念说明实际效果。",
        }])
        self.assertNotIn("problem", result[0])
        self.assertNotIn("solution", result[0])

    def test_difficulty_names_use_confirmed_table(self):
        self.assertEqual(difficulty_name(6), "极易")
        self.assertEqual(difficulty_name(13), "困难")
        self.assertEqual(difficulty_name(18), "炼狱")
        with self.assertRaises(CheckError):
            difficulty_name(17)

    def test_normalize_dc_accepts_integer_and_chinese_difficulty(self):
        self.assertEqual(normalize_dc(8), 8)
        self.assertEqual(normalize_dc("容易"), 8)
        self.assertEqual(normalize_dc("中等"), 10)

    def test_normalize_dc_rejects_unknown_difficulty(self):
        with self.assertRaises(CheckError):
            normalize_dc("很难")

    def test_passive_boundary_succeeds_at_equal_total(self):
        result = passive_check(SKILL, dc=13, situational=[])
        self.assertEqual(result["total"], 13)
        self.assertTrue(result["success"])

    def test_modifier_parser_rejects_duplicate_labels(self):
        with self.assertRaisesRegex(CheckError, "duplicate"):
            parse_situational_modifiers(["已经写下记录=1", "已经写下记录=1"])

    def test_active_check_reports_auditable_success(self):
        result = active_check(
            SKILL,
            dc=14,
            situational=[{"label": "已完成工具校准", "value": 1}],
            dice=(3, 4),
        )
        self.assertEqual(result["total"], 15)
        self.assertTrue(result["success"])
        self.assertEqual(result["dice"], [3, 4])

    def test_double_one_auto_fails(self):
        result = active_check(SKILL, dc=6, situational=[], dice=(1, 1))
        self.assertFalse(result["success"])
        self.assertEqual(result["automatic"], "double-one")

    def test_double_six_auto_succeeds(self):
        result = active_check(SKILL, dc=20, situational=[], dice=(6, 6))
        self.assertTrue(result["success"])
        self.assertEqual(result["automatic"], "double-six")


if __name__ == "__main__":
    unittest.main()
