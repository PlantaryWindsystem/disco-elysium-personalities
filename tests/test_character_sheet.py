from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from character_sheet import (  # noqa: E402
    CANONICAL_PERSONALITIES,
    CharacterSheetError,
    calculate_effective_skill,
    validate_sheet_data,
)


BASE_SKILLS = {name: 3 for name in CANONICAL_PERSONALITIES}
BASE_SKILLS["内陆帝国"] = 4


def valid_sheet() -> dict:
    return {
        "version": 1,
        "onboarding_status": "confirmed",
        "attributes": {"智力": 3, "精神": 3, "体格": 3, "身手": 3},
        "signature_skill": "内陆帝国",
        "base_skills": dict(BASE_SKILLS),
        "confirmed_at": "2026-08-10T05:00:00+08:00",
    }


class CharacterSheetTests(unittest.TestCase):
    def test_accepts_confirmed_12_point_sheet(self):
        sheet = validate_sheet_data(valid_sheet())
        self.assertEqual(sum(sheet["attributes"].values()), 12)
        self.assertEqual(set(sheet["base_skills"]), set(CANONICAL_PERSONALITIES))

    def test_rejects_attribute_total_other_than_12(self):
        data = valid_sheet()
        data["attributes"]["身手"] = 4
        with self.assertRaisesRegex(CharacterSheetError, "sum to 12"):
            validate_sheet_data(data)

    def test_rejects_attribute_outside_one_to_six(self):
        data = valid_sheet()
        data["attributes"] = {"智力": 7, "精神": 2, "体格": 2, "身手": 1}
        with self.assertRaisesRegex(CharacterSheetError, "between 1 and 6"):
            validate_sheet_data(data)

    def test_rejects_noncanonical_skill(self):
        data = valid_sheet()
        data["base_skills"]["坚忍持重"] = data["base_skills"].pop("坚忍不拔")
        with self.assertRaisesRegex(CharacterSheetError, "canonical"):
            validate_sheet_data(data)

    def test_applies_research_and_completed_thoughts_without_mutating_base(self):
        thoughts = {
            "thoughts": [
                {
                    "name": "工具使用研究",
                    "status": "研究中",
                    "temporary_research_bonus": ["+1 逻辑思维", "-1 平心定气"],
                    "completion_effect": ["+1 博学多闻"],
                },
                {
                    "name": "记录已经完成",
                    "status": "已内在化",
                    "temporary_research_bonus": ["-1 同舟共济"],
                    "completion_effect": ["+1 同舟共济", "工具操作相关的逻辑思维检定 +1"],
                },
            ]
        }
        sheet = valid_sheet()
        result = calculate_effective_skill(sheet, thoughts, "逻辑思维", {"工具操作相关"})
        self.assertEqual(result["base"], 3)
        self.assertEqual(result["thought_total"], 2)
        self.assertEqual(result["effective"], 5)
        self.assertEqual(sheet["base_skills"]["逻辑思维"], 3)

    def test_conditional_effect_requires_exact_condition(self):
        thoughts = {
            "thoughts": [{
                "name": "记录已经完成",
                "status": "已内在化",
                "completion_effect": ["工具操作相关的逻辑思维检定 +1"],
            }]
        }
        result = calculate_effective_skill(valid_sheet(), thoughts, "逻辑思维", set())
        self.assertEqual(result["effective"], 3)


if __name__ == "__main__":
    unittest.main()
