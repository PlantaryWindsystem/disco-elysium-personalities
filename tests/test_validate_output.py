import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_output import validate_text

class SyntheticOutputTests(unittest.TestCase):
    def test_popup_is_standalone(self):
        self.assertEqual([],validate_text('> **获得思维：扳手备忘录（Earth）**\n> [内在化]　[放入思维阁]'))
        self.assertTrue(validate_text('> **获得思维：扳手备忘录（Earth）** [内在化]　[放入思维阁]'))
    def test_lists_and_multiple_paragraphs_rejected(self):
        for body in ('> - 转动旋钮。','> 一段。\n>\n> 第二段。'):
            self.assertTrue(validate_text('> 🟨 **能工巧匠【容易：成功】**\n'+body))
    def test_voice_can_return(self):
        text='> 🟨 **能工巧匠【容易：成功】**\n> 咔哒。\n\n> 🟨 **能工巧匠【容易：成功】**\n> 转动半圈。'
        self.assertEqual([],validate_text(text))
    def test_failure_can_have_distinct_voice(self):
        self.assertEqual([],validate_text('> 🟦 **逻辑思维【容易：失败】**\n> 呃……再想想。'))
    def test_truncated_earth_card_rejected(self):
        text='> **扳手备忘录（Earth）**\n> **研究完成效果：** +1 能工巧匠\n> **研究时间：** 2 次有效推进\n> **获取方式：** 完成一次操作\n> **问题：** 零件松了。\n> **解答：** 重新校准。'
        self.assertTrue(validate_text(text))
