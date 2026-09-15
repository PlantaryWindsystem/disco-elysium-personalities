from __future__ import annotations
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import package_skill
import validate_output

class MaintenanceRegressionTests(unittest.TestCase):
    def test_package_omits_private_root_and_hidden_work_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'source'
            paths = ['SKILL.md', 'LICENSE', 'references/人物卡.md',
                     'scripts/runtime_context.py', 'assets/sample.md',
                     '.draft-private.md', '_draft-current.md', 'notes.md',
                     'scripts/.runtime-private.json', 'references/.draft-private.md',
                     'backups/SKILL.md', 'state/character-sheet.yaml',
                     'tests/test_x.py', 'scripts/__pycache__/x.pyc']
            for name in paths:
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture', encoding='utf-8')
            output = Path(directory)/'new.skill'
            with patch.object(package_skill, 'SKILL_ROOT', root):
                package_skill.build_package(output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {
                    'SKILL.md', 'LICENSE', 'references/人物卡.md',
                    'scripts/runtime_context.py', 'assets/sample.md'})
            self.assertTrue(all((root/name).exists() for name in paths))
            with patch.object(package_skill, 'SKILL_ROOT', root):
                with self.assertRaises(FileExistsError):
                    package_skill.build_package(output)

    def test_sensory_suffix_is_only_valid_for_perception(self):
        invalid = '> 🟦 **逻辑思维（视觉）【容易：成功】**\n> 细节。'
        valid = '> 🟨 **五感发达（视觉）【容易：成功】**\n> 红色。'
        self.assertTrue(validate_output.validate_text(invalid))
        self.assertEqual([], validate_output.validate_text(valid))

    def test_missing_or_non_boolean_success_cannot_match_failure(self):
        draft = '> 🟦 **逻辑思维【容易：失败】**\n> 呃……空白。'
        for value in (None, 0, '', 'false'):
            item = {'skill': '逻辑思维', 'difficulty': '容易'}
            if value is not None:
                item['success'] = value
            with self.subTest(value=value):
                self.assertTrue(validate_output.validate_text(draft, {'checks': [item]}))

    def test_cli_cannot_report_full_validation_without_check_records(self):
        draft = '> 🟦 **逻辑思维【容易：成功】**\n> 啊，明白了。'
        with patch('sys.stdin', io.StringIO(draft)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, validate_output.main([]))

    def test_cli_accepts_current_check_record_and_special_only_output(self):
        draft = '> 🟦 **逻辑思维【容易：失败】**\n> 呃……空白。'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'checks.json'
            path.write_text(json.dumps({'checks': [{'skill':'逻辑思维', 'difficulty':'容易', 'success':False}]}), encoding='utf-8')
            with patch('sys.stdin', io.StringIO(draft)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, validate_output.main(['--runtime-json', str(path)]))
        with patch('sys.stdin', io.StringIO('> ⬛ **脊髓**\n> 动一下。')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, validate_output.main([]))

    def test_official_elysium_prose_preserves_contrast_but_earth_does_not(self):
        source=(ROOT/'references/思维阁-极乐世界.md').read_text(encoding='utf-8')
        section=source.split('## 产能过剩的荣誉腺体',1)[1].split('\n## ',1)[0]
        problem=next(line.removeprefix('**问题：**') for line in section.splitlines() if line.startswith('**问题：**'))
        answer=next(line.removeprefix('**解答：**') for line in section.splitlines() if line.startswith('**解答：**'))
        draft=f'> **产能过剩的荣誉腺体（Elysium）**\n> **研究完成效果：** +1 逻辑思维\n> **研究时间：** 2 次有效推进\n> **获取方式：** 原文测试\n> **问题：** {problem}\n> **解答：** {answer}'
        self.assertEqual([], validate_output.validate_text(draft))
        errors=validate_output.validate_text(draft.replace('（Elysium）','（Earth）'))
        self.assertTrue(any('forbidden contrast' in error for error in errors))

    def test_reviewed_redundant_attribute_can_be_omitted_without_changing_candidates(self):
        names=['争强好胜','通情达理','内陆帝国']
        draft='\n\n'.join(f'> 🟪 **{name}【容易：成功】**\n> 啊。' for name in names)
        runtime={'candidate_attributes':['精神','智力'], 'checks':[{'skill':name,'difficulty':'容易','success':True} for name in names]}
        self.assertTrue(any('single-color collapse' in error for error in validate_output.validate_text(draft,runtime)))
        runtime['routing_review']={'excluded_attributes':{'智力':'逻辑思维的判断与现有声音重复，未提供独立线索。'}}
        self.assertEqual([],validate_output.validate_text(draft,runtime))
        runtime['routing_review']['excluded_attributes']['智力']=''
        self.assertTrue(any('single-color collapse' in error for error in validate_output.validate_text(draft,runtime)))

    def test_repeated_same_voice_is_not_three_different_personalities(self):
        draft='\n\n'.join('> 🟪 **内陆帝国【容易：成功】**\n> 啊。' for _ in range(3))
        runtime={'candidate_attributes':['精神','智力'],'checks':[{'skill':'内陆帝国','difficulty':'容易','success':True}]}
        self.assertEqual([],validate_output.validate_text(draft,runtime))
