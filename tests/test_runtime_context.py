from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MODULE_PATH = SCRIPTS / "runtime_context.py"
INDEX_PATH = ROOT / "references" / "运行时人格索引.json"

sys.path.insert(0, str(SCRIPTS))


def load_runtime_module():
    if not MODULE_PATH.is_file():
        return None
    return importlib.import_module("runtime_context")


class RuntimeContextTests(unittest.TestCase):
    def test_due_trigger_requires_explicit_candidate_review(self):
        runtime = load_runtime_module()
        thoughts = {"version": 1, "thoughts": []}

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "thought-trigger-state.yaml"
            state_path.write_text(
                yaml.safe_dump({
                    "version": 1,
                    "thought_ids_fingerprint": runtime.thought_ids_fingerprint(thoughts),
                    "turns_since_new_thought": 20,
                    "next_due_turn": 15,
                    "last_substantive_turn_hash": None,
                }, allow_unicode=True),
                encoding="utf-8",
            )
            result = runtime.update_thought_trigger_state(
                thoughts, state_path, "no-candidate", substantive=True,
                candidate=None,
            )

        self.assertEqual(result["status"], "due")
        self.assertFalse(result["candidate_ready"])
        self.assertFalse(result["should_unlock"])
        self.assertTrue(result["review_required"])
        self.assertEqual(result["overdue_by"], 6)

    def test_no_candidate_review_defers_and_reopens(self):
        runtime = load_runtime_module()
        thoughts = {"version": 1, "thoughts": []}

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "thought-trigger-state.yaml"
            state_path.write_text(
                yaml.safe_dump({
                    "version": 1,
                    "thought_ids_fingerprint": runtime.thought_ids_fingerprint(thoughts),
                    "turns_since_new_thought": 20,
                    "next_due_turn": 15,
                    "last_substantive_turn_hash": None,
                }, allow_unicode=True),
                encoding="utf-8",
            )
            reviewed = runtime.update_thought_trigger_state(
                thoughts,
                state_path,
                "review-turn",
                substantive=True,
                candidate=None,
                review={
                    "result": "no-mature-candidate",
                    "reason": "当前材料仍然只是同一情绪的延长，没有形成新的可复用机制。",
                },
            )
            first_deferred = runtime.update_thought_trigger_state(
                thoughts, state_path, "deferred-1", substantive=True,
            )
            second_deferred = runtime.update_thought_trigger_state(
                thoughts, state_path, "deferred-2", substantive=True,
            )
            reopened = runtime.update_thought_trigger_state(
                thoughts, state_path, "reopen", substantive=True,
            )

        self.assertFalse(reviewed["review_required"])
        self.assertEqual(reviewed["review_deferred_until"], 24)
        self.assertFalse(first_deferred["review_required"])
        self.assertFalse(second_deferred["review_required"])
        self.assertTrue(reopened["review_required"])

    def test_candidate_review_rejects_empty_or_unknown_review(self):
        runtime = load_runtime_module()

        self.assertFalse(runtime.assess_thought_review(None)["valid"])
        self.assertFalse(runtime.assess_thought_review({
            "result": "no-mature-candidate",
            "reason": "",
        })["valid"])
        self.assertFalse(runtime.assess_thought_review({
            "result": "skip-forever",
            "reason": "没有。",
        })["valid"])
        self.assertTrue(runtime.assess_thought_review({
            "result": "no-mature-candidate",
            "reason": "当前只有一次性的情绪变化，还没有形成可复用机制。",
        })["valid"])

    def test_candidate_gate_accepts_reusable_mechanism_and_rejects_empty_mood(self):
        runtime = load_runtime_module()
        existing = {"version": 1, "thoughts": [{"id": "existing", "name": "旧思维"}]}
        good = {
            "id": "earth-good",
            "name": "候选思维",
            "source": "Earth",
            "mechanism": "把普通关照误认为必须先制造危机才能获得的奖励",
            "problem": "一个可以继续研究的问题",
            "acquisition": "一个具体经历",
        }
        bad = {"id": "earth-bad", "name": "只是更阴沉", "source": "Earth"}

        self.assertTrue(runtime.assess_thought_candidate(good, existing)["eligible"])
        self.assertFalse(runtime.assess_thought_candidate(bad, existing)["eligible"])

    def test_output_policy_surfaces_only_contributing_personalities_and_keeps_atmosphere_voice(self):
        runtime = load_runtime_module()
        candidates = [
            {"name": "逻辑思维", "success": True, "contribution": "new-fact", "priority": 2},
            {"name": "平心定气", "success": False, "failure_type": "silent", "priority": 3},
            {"name": "内陆帝国", "success": False, "failure_type": "misread", "surface": True, "priority": 1},
        ]
        visible = runtime.select_visible_candidates(candidates, limit=2)
        self.assertEqual([item["name"] for item in visible], ["逻辑思维", "内陆帝国"])

        special = runtime.select_visible_special_voices([
            {"name": "古老的爬虫脑", "function": "atmosphere", "surface": True},
        ])
        self.assertEqual([item["name"] for item in special], ["古老的爬虫脑"])
    def test_runtime_module_and_index_exist(self):
        self.assertTrue(MODULE_PATH.is_file(), "runtime context module is missing")
        self.assertTrue(INDEX_PATH.is_file(), "generated runtime index is missing")

    def test_generated_index_covers_canonical_personalities(self):
        runtime = load_runtime_module()
        if runtime is None:
            self.skipTest("runtime context module is not implemented yet")

        generated = runtime.build_runtime_index(ROOT / "references")

        self.assertEqual(
            set(generated["profiles"]),
            set(runtime.CANONICAL_PERSONALITIES),
        )
        for name, profile in generated["profiles"].items():
            self.assertEqual(profile["name"], name)
            self.assertIn(profile["color"], {"🟦", "🟪", "🟥", "🟨"})
            self.assertIn(profile["attribute"], {"智力", "精神", "体格", "身手"})
            for field in ("core_action", "success", "failure", "rhythm", "boundary"):
                self.assertTrue(profile[field].strip(), f"{name} lacks {field}")
            self.assertEqual(len(profile["source_sha256"]), 64)
            self.assertGreaterEqual(len(profile["samples"]), 2)

    def test_checked_in_index_matches_reference_sources(self):
        runtime = load_runtime_module()
        if runtime is None or not INDEX_PATH.is_file():
            self.skipTest("runtime index is not implemented yet")

        checked_in = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        generated = runtime.build_runtime_index(ROOT / "references")

        self.assertEqual(checked_in, generated)

    def test_runtime_payload_returns_only_selected_profiles_and_existing_checks(self):
        runtime = load_runtime_module()
        if runtime is None or not INDEX_PATH.is_file():
            self.skipTest("runtime index is not implemented yet")

        sheet = {
            "version": 1,
            "onboarding_status": "confirmed",
            "attributes": {"智力": 5, "精神": 3, "体格": 2, "身手": 2},
            "signature_skill": "内陆帝国",
            "base_skills": {name: 3 for name in runtime.CANONICAL_PERSONALITIES},
            "confirmed_at": "2026-08-12T00:00:00+08:00",
        }
        sheet["base_skills"]["天人感应"] = 6
        thoughts = {
            "version": 1,
            "thoughts": [{
                "id": "earth-test",
                "name": "测试思维",
                "status": "研究中",
                "progress": 1,
                "required_progress": 2,
                "progress_cues": ["出现新的判断"],
                "temporary_research_bonus": ["+1 天人感应"],
                "progress_log": [],
            }],
        }
        request = {
            "profiles": ["天人感应", "同舟共济"],
            "candidate_attributes": ["体格", "精神", "身手"],
            "special_voices": ["古老的爬虫脑"],
            "turn_key": "runtime-payload-test",
            "substantive": True,
            "checks": [{
                "skill": "天人感应",
                "dc": 10,
                "conditions": [],
                "modifiers": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            sheet_path = temp / "character-sheet.yaml"
            thoughts_path = temp / "thought-cabinet.yaml"
            trigger_path = temp / "thought-trigger-state.yaml"
            sheet_path.write_text(
                yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            thoughts_path.write_text(
                yaml.safe_dump(thoughts, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            payload = runtime.build_runtime_payload(
                request,
                index_path=INDEX_PATH,
                sheet_path=sheet_path,
                thoughts_path=thoughts_path,
                trigger_path=trigger_path,
            )

        self.assertEqual([item["name"] for item in payload["profiles"]], ["天人感应", "同舟共济"])
        self.assertEqual(payload["candidate_attributes"], ["体格", "精神", "身手"])
        self.assertEqual([item["name"] for item in payload["special_voices"]], ["古老的爬虫脑"])
        self.assertEqual(payload["checks"][0]["skill"], "天人感应")
        self.assertTrue(payload["checks"][0]["success"])
        self.assertEqual(payload["thought_audit"][0]["name"], "测试思维")
        self.assertEqual(payload["thought_trigger"]["turns_since_new_thought"], 1)
        self.assertEqual(payload["thought_trigger"]["status"], "normal")

    def test_minimal_runtime_keeps_explicit_special_voice_without_counting_thought_turn(self):
        runtime = load_runtime_module()
        thoughts = {
            "version": 1,
            "thoughts": [{"id": "earth-existing", "acquired_at": "2026-08-13T09:00:00+08:00"}],
        }
        request = {
            "runtime_mode": "minimal",
            "profiles": [],
            "special_voices": ["古老的爬虫脑"],
            "turn_key": "minimal-command",
            "substantive": False,
            "checks": [],
        }

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            thoughts_path = temp / "thought-cabinet.yaml"
            trigger_path = temp / "thought-trigger-state.yaml"
            thoughts_path.write_text(
                yaml.safe_dump(thoughts, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            payload = runtime.build_runtime_payload(
                request,
                index_path=INDEX_PATH,
                thoughts_path=thoughts_path,
                trigger_path=trigger_path,
            )

        self.assertEqual(payload["runtime_mode"], "minimal")
        self.assertEqual([item["name"] for item in payload["special_voices"]], ["古老的爬虫脑"])
        self.assertNotIn("thought_audit", payload)
        self.assertNotIn("thought_trigger", payload)
        self.assertFalse(trigger_path.exists())

    def test_standard_runtime_keeps_thought_audit_and_trigger(self):
        runtime = load_runtime_module()
        thoughts = {
            "version": 1,
            "thoughts": [{
                "id": "earth-standard",
                "name": "标准思维",
                "status": "研究中",
                "progress": 1,
                "required_progress": 2,
                "progress_cues": ["出现新的判断"],
                "progress_log": [],
            }],
        }
        request = {
            "runtime_mode": "standard",
            "profiles": ["逻辑思维"],
            "special_voices": [],
            "turn_key": "standard-turn",
            "substantive": True,
            "checks": [{
                "skill": "逻辑思维",
                "dc": "容易",
                "conditions": [],
                "modifiers": [],
            }],
        }

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            sheet_path = temp / "character-sheet.yaml"
            thoughts_path = temp / "thought-cabinet.yaml"
            trigger_path = temp / "thought-trigger-state.yaml"
            sheet = {
                "version": 1,
                "onboarding_status": "confirmed",
                "attributes": {"智力": 5, "精神": 3, "体格": 2, "身手": 2},
                "signature_skill": "内陆帝国",
                "base_skills": {name: 3 for name in runtime.CANONICAL_PERSONALITIES},
                "confirmed_at": "2026-08-12T00:00:00+08:00",
            }
            sheet_path.write_text(
                yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            thoughts_path.write_text(
                yaml.safe_dump(thoughts, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            payload = runtime.build_runtime_payload(
                request,
                index_path=INDEX_PATH,
                sheet_path=sheet_path,
                thoughts_path=thoughts_path,
                trigger_path=trigger_path,
            )

        self.assertEqual(payload["runtime_mode"], "standard")
        self.assertEqual(payload["checks"][0]["dc"], 8)
        self.assertEqual(payload["thought_audit"][0]["name"], "标准思维")
        self.assertEqual(payload["thought_trigger"]["turns_since_new_thought"], 1)

    def test_missing_or_unknown_runtime_mode_defaults_to_standard(self):
        runtime = load_runtime_module()
        thoughts = {"version": 1, "thoughts": []}

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            thoughts_path = temp / "thought-cabinet.yaml"
            trigger_path = temp / "thought-trigger-state.yaml"
            thoughts_path.write_text(
                yaml.safe_dump(thoughts, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            for value in (None, "unknown", []):
                request = {
                    "profiles": [],
                    "special_voices": [],
                    "turn_key": f"fallback-{value}",
                    "substantive": False,
                    "checks": [],
                }
                if value is not None:
                    request["runtime_mode"] = value
                payload = runtime.build_runtime_payload(
                    request,
                    index_path=INDEX_PATH,
                    thoughts_path=thoughts_path,
                    trigger_path=trigger_path,
                )
                self.assertEqual(payload["runtime_mode"], "standard")
                self.assertIn("thought_audit", payload)
                self.assertIn("thought_trigger", payload)

    def test_thought_trigger_counts_unique_substantive_turns_once(self):
        runtime = load_runtime_module()
        thoughts = {
            "version": 1,
            "thoughts": [{
                "id": "earth-existing",
                "acquired_at": "2026-08-13T09:00:00+08:00",
            }],
        }

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "thought-trigger-state.yaml"
            first = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-1", substantive=True
            )
            repeated = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-1", substantive=True
            )
            administrative = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-2", substantive=False
            )
            second = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-3", substantive=True
            )

        self.assertEqual(first["turns_since_new_thought"], 1)
        self.assertTrue(first["counted"])
        self.assertEqual(repeated["turns_since_new_thought"], 1)
        self.assertFalse(repeated["counted"])
        self.assertEqual(administrative["turns_since_new_thought"], 1)
        self.assertFalse(administrative["counted"])
        self.assertEqual(second["turns_since_new_thought"], 2)
        self.assertTrue(second["counted"])

    def test_thought_trigger_becomes_due_between_15_and_25_and_resets_on_new_thought(self):
        runtime = load_runtime_module()
        thoughts = {
            "version": 1,
            "thoughts": [{
                "id": "earth-existing",
                "acquired_at": "2026-08-13T09:00:00+08:00",
            }],
        }

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "thought-trigger-state.yaml"
            state = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-1", substantive=True
            )
            due_turn = state["next_due_turn"]
            self.assertGreaterEqual(due_turn, 15)
            self.assertLessEqual(due_turn, 25)

            for number in range(2, due_turn + 1):
                state = runtime.update_thought_trigger_state(
                    thoughts, state_path, f"turn-{number}", substantive=True
                )

            self.assertEqual(state["turns_since_new_thought"], due_turn)
            self.assertEqual(state["status"], "due")
            self.assertFalse(state["candidate_ready"])
            self.assertFalse(state["should_unlock"])

            thoughts["thoughts"].append({
                "id": "earth-new",
                "acquired_at": "2026-08-13T10:00:00+08:00",
            })
            reset = runtime.update_thought_trigger_state(
                thoughts, state_path, "turn-after-new-thought", substantive=True
            )

        self.assertEqual(reset["turns_since_new_thought"], 1)
        self.assertEqual(reset["status"], "normal")
        self.assertFalse(reset["should_unlock"])


if __name__ == "__main__":
    unittest.main()
