from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_skill import build_package  # noqa: E402


class PackageSkillTests(unittest.TestCase):
    def test_package_preserves_runtime_directories_and_excludes_work_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "skill.skill"
            build_package(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("SKILL.md", names)
            self.assertIn("references/人物卡.md", names)
            self.assertIn("references/检定系统.md", names)
            self.assertIn("scripts/character_sheet.py", names)
            self.assertIn("scripts/check_engine.py", names)
            self.assertIn("scripts/runtime_context.py", names)
            self.assertIn("references/运行时人格索引.json", names)
            self.assertFalse(any(name.startswith("backups/") for name in names))
            self.assertFalse(any(name.startswith("tests/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))


if __name__ == "__main__":
    unittest.main()
