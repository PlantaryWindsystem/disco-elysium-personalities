import importlib
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ThoughtStateTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("thought_state")

    def initial_state(self):
        return {
            "version": 1,
            "thoughts": [{
                "id": "earth-existing",
                "name": "旧思维",
                "source": "Earth",
                "status": "已内在化",
                "progress": 2,
                "required_progress": 2,
                "progress_log": [],
            }],
        }

    def test_acquire_appends_and_reloads_without_losing_existing_thoughts(self):
        new_thought = {
            "id": "earth-new",
            "name": "新思维",
            "source": "Earth",
            "status": "已获得",
            "progress": 0,
            "required_progress": 3,
            "progress_log": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "thought-cabinet.yaml"
            path.write_text(yaml.safe_dump(self.initial_state(), allow_unicode=True), encoding="utf-8")

            result = self.module.apply_operation(path, "acquire", thought=new_thought)

            self.assertTrue(result["verified"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["id"] for item in saved["thoughts"]],
                ["earth-existing", "earth-new"],
            )

    def test_repeating_acquire_is_idempotent_and_transition_preserves_other_entries(self):
        new_thought = {
            "id": "earth-new",
            "name": "新思维",
            "source": "Earth",
            "status": "已获得",
            "progress": 0,
            "required_progress": 3,
            "progress_log": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "thought-cabinet.yaml"
            path.write_text(yaml.safe_dump(self.initial_state(), allow_unicode=True), encoding="utf-8")

            self.module.apply_operation(path, "acquire", thought=new_thought)
            repeated = self.module.apply_operation(path, "acquire", thought=new_thought)
            started = self.module.apply_operation(path, "start_research", thought_id="earth-new")

            self.assertTrue(repeated["idempotent"])
            self.assertEqual(started["thought"]["status"], "研究中")
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["thoughts"][0]["id"], "earth-existing")
            self.assertEqual(saved["thoughts"][1]["status"], "研究中")

    def test_invalid_duplicate_ids_are_rejected_before_write(self):
        bad_state = self.initial_state()
        bad_state["thoughts"].append(dict(bad_state["thoughts"][0]))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "thought-cabinet.yaml"
            path.write_text(yaml.safe_dump(bad_state, allow_unicode=True), encoding="utf-8")

            with self.assertRaises(self.module.ThoughtStateError):
                self.module.apply_operation(path, "validate")

    def test_research_progress_and_internalization_are_checked_and_persisted(self):
        thought = {
            "id": "earth-research",
            "name": "研究思维",
            "source": "Earth",
            "status": "已获得",
            "progress": 0,
            "required_progress": 2,
            "progress_log": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "thought-cabinet.yaml"
            path.write_text(yaml.safe_dump({"version": 1, "thoughts": []}, allow_unicode=True), encoding="utf-8")
            self.module.apply_operation(path, "acquire", thought=thought)
            self.module.apply_operation(path, "place", thought_id="earth-research")
            self.module.apply_operation(path, "start_research", thought_id="earth-research")
            self.module.apply_operation(path, "progress", thought_id="earth-research", note="新的材料")
            self.module.apply_operation(path, "progress", thought_id="earth-research", note="新的决定")
            result = self.module.apply_operation(path, "internalize", thought_id="earth-research")

        self.assertEqual(result["thought"]["status"], "已内在化")
        self.assertEqual(result["thought"]["progress"], 2)
        self.assertEqual(len(result["thought"]["progress_log"]), 2)


if __name__ == "__main__":
    unittest.main()
