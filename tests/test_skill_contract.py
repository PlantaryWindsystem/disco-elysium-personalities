from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_required_references_exist(self):
        self.assertTrue((ROOT / "references" / "人物卡.md").is_file())
        self.assertTrue((ROOT / "references" / "检定系统.md").is_file())

    def test_skill_requires_first_use_attribute_discussion(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("首次启用时，第一件事是讨论四属性分配", text)
        self.assertIn("character-sheet.yaml", text)
        self.assertIn("被动检定", text)
        self.assertIn("主动检定", text)
        self.assertIn("双 1", text)
        self.assertIn("双 6", text)

    def test_thought_rules_use_calculated_modifiers(self):
        text = (ROOT / "references" / "思维阁.md").read_text(encoding="utf-8")
        self.assertIn("进入检定算式", text)
        self.assertNotIn("提高相关人格被选中和成功的倾向", text)

    def test_check_rules_protect_safety_critical_content(self):
        text = (ROOT / "references" / "检定系统.md").read_text(encoding="utf-8")
        self.assertIn("不由骰子决定", text)
        self.assertIn("失败人格可以发言", text)

    def test_validator_knows_hybrid_check_contract(self):
        text = (ROOT / "scripts" / "validate_embodied_routing.py").read_text(encoding="utf-8")
        self.assertIn("references/人物卡.md", text)
        self.assertIn("references/检定系统.md", text)
        self.assertIn("首次启用时，第一件事是讨论四属性分配", text)
        self.assertIn("双 1", text)
        self.assertIn("双 6", text)

    def test_skill_uses_runtime_index_with_full_reference_fallback(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("运行时人格索引", text)
        self.assertIn("runtime_context.py", text)
        self.assertIn("原文", text)

    def test_skill_tracks_lightweight_thought_trigger_cadence(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        thoughts = (ROOT / "references" / "思维阁.md").read_text(encoding="utf-8")

        self.assertIn("turn_key", skill)
        self.assertIn("thought_trigger", skill)
        self.assertIn("15~25", skill)
        self.assertIn("第 10 轮", thoughts)
        self.assertIn("15~25", thoughts)
        self.assertIn("不增加模型调用", thoughts)

    def test_skill_documents_runtime_tiers_without_dropping_quality_guards(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("minimal", text)
        self.assertIn("standard", text)
        self.assertIn("deep", text)
        self.assertIn("显式召唤特殊脑内声音", text)
        self.assertIn("直接跳过 `runtime_context.py`", text)
        self.assertIn("思维触发", text)
        self.assertNotIn("纯命令也必须运行完整思维审计", text)

    def test_skill_allows_selective_voice_rendering_and_atmospheric_special_voices(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        special = (ROOT / "references" / "特殊脑内声音.md").read_text(encoding="utf-8")
        thoughts = (ROOT / "references" / "思维阁.md").read_text(encoding="utf-8")

        self.assertIn("失败人格可以发言", skill)
        self.assertIn("失败人格若出场", skill)
        self.assertNotIn("失败人格默认保持沉默", skill)
        self.assertIn("检定标题固定使用", skill)
        self.assertIn("不强制每个内部检定都渲染", skill)
        self.assertIn("纯氛围", special)
        self.assertIn("候选成熟度", thoughts)
        self.assertIn("不因期限强行生成思维", thoughts)

    def test_skill_forbids_report_lists_and_repeats_voice_for_new_paragraphs(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("禁止报告式分点", skill)
        self.assertIn("一个声音块只留一个自然段", skill)
        self.assertIn("宁可重复声音，不要拆成提纲", skill)

    def test_skill_requires_voice_identity_and_conditional_color_diversity(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("删除人格标题后", skill)
        self.assertIn("不能互换人格名", skill)
        self.assertIn("跨属性候选复核", skill)
        self.assertIn("避免单色塌缩", skill)
        self.assertIn("不采用固定四色配额", skill)

    def test_skill_requires_due_thought_candidate_review_retry(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        thoughts = (ROOT / "references" / "思维阁.md").read_text(encoding="utf-8")

        self.assertIn("review_required", skill)
        self.assertIn("thought_review", skill)
        self.assertIn("相同 `turn_key`", skill)
        self.assertIn("候选复核退避", thoughts)


if __name__ == "__main__":
    unittest.main()
