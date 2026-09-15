from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from character_sheet import (
    DEFAULT_SHEET_PATH,
    DEFAULT_THOUGHT_PATH,
    calculate_effective_skill,
    load_sheet,
    load_yaml,
)

DIFFICULTIES = {
    6: "极易", 7: "极易",
    8: "容易", 9: "容易",
    10: "中等", 11: "中等",
    12: "挑战", 13: "困难", 14: "极难", 15: "专家", 16: "噩梦",
    18: "炼狱", 19: "炼狱", 20: "炼狱",
}
DEFAULT_LOG_PATH = DEFAULT_SHEET_PATH.parent / "check-log.jsonl"


class CheckError(ValueError):
    """Raised when a check cannot be computed without guessing."""


def difficulty_name(dc: int) -> str:
    try:
        return DIFFICULTIES[dc]
    except KeyError as exc:
        raise CheckError(f"unsupported target value: {dc}") from exc


def normalize_dc(value: int | str) -> int:
    """Accept a numeric target or one of the confirmed Chinese difficulty labels."""
    if isinstance(value, bool):
        raise CheckError("dc must be an integer or confirmed difficulty label")
    if isinstance(value, int):
        difficulty_name(value)
        return value
    if isinstance(value, str):
        labels = {
            label: min(target for target, name in DIFFICULTIES.items() if name == label)
            for label in set(DIFFICULTIES.values())
        }
        try:
            return labels[value.strip()]
        except KeyError as exc:
            raise CheckError(f"unsupported difficulty label: {value}") from exc
    raise CheckError("dc must be an integer or confirmed difficulty label")


def parse_situational_modifiers(values: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    labels: set[str] = set()
    for raw in values:
        label, separator, number = raw.rpartition("=")
        if not separator or not label.strip():
            raise CheckError(f"modifier must use label=value: {raw}")
        label = label.strip()
        if label in labels:
            raise CheckError(f"duplicate modifier label: {label}")
        try:
            value = int(number)
        except ValueError as exc:
            raise CheckError(f"modifier value must be an integer: {raw}") from exc
        if abs(value) > 3:
            raise CheckError("situational modifiers above 3 require a separate explicit rule")
        labels.add(label)
        parsed.append({"label": label, "value": value})
    return parsed


def passive_check(skill: dict[str, Any], dc: int, situational: list[dict[str, Any]]) -> dict[str, Any]:
    difficulty = difficulty_name(dc)
    situation_total = sum(item["value"] for item in situational)
    total = 6 + skill["effective"] + situation_total
    return {
        "mode": "passive",
        "skill": skill["skill"],
        "difficulty": difficulty,
        "dc": dc,
        "base": skill["base"],
        "thought_modifiers": skill["thought_modifiers"],
        "thought_total": skill["thought_total"],
        "effective_skill": skill["effective"],
        "situational_modifiers": situational,
        "situational_total": situation_total,
        "constant": 6,
        "total": total,
        "success": total >= dc,
    }


def active_check(
    skill: dict[str, Any],
    dc: int,
    situational: list[dict[str, Any]],
    dice: tuple[int, int] | None = None,
) -> dict[str, Any]:
    difficulty = difficulty_name(dc)
    if dice is None:
        rng = secrets.SystemRandom()
        dice = (rng.randint(1, 6), rng.randint(1, 6))
    if len(dice) != 2 or any(value < 1 or value > 6 for value in dice):
        raise CheckError("dice must contain two values from 1 to 6")
    situation_total = sum(item["value"] for item in situational)
    total = sum(dice) + skill["effective"] + situation_total
    automatic = "double-one" if dice == (1, 1) else "double-six" if dice == (6, 6) else None
    success = False if automatic == "double-one" else True if automatic == "double-six" else total >= dc
    return {
        "mode": "active",
        "skill": skill["skill"],
        "difficulty": difficulty,
        "dc": dc,
        "dice": list(dice),
        "base": skill["base"],
        "thought_modifiers": skill["thought_modifiers"],
        "thought_total": skill["thought_total"],
        "effective_skill": skill["effective"],
        "situational_modifiers": situational,
        "situational_total": situation_total,
        "total": total,
        "automatic": automatic,
        "success": success,
    }


def write_log(result: dict[str, Any], path: Path = DEFAULT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(result)
    entry["recorded_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def skill_context(
    skill_name: str,
    sheet_path: Path,
    thoughts_path: Path,
    conditions: list[str],
) -> dict[str, Any]:
    sheet = load_sheet(sheet_path)
    thoughts = load_yaml(thoughts_path)
    return calculate_effective_skill(sheet, thoughts, skill_name, set(conditions))


def active_thought_audit(thought_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact semantic cues for thoughts that are still being researched."""
    active: list[dict[str, Any]] = []
    for thought in thought_state.get("thoughts", []):
        if thought.get("status") != "研究中":
            continue
        progress_log = thought.get("progress_log") or []
        latest_note = None
        if progress_log and isinstance(progress_log[-1], dict):
            latest_note = progress_log[-1].get("note")
        cues = thought.get("progress_cues") or []
        if not isinstance(cues, list):
            cues = []
        active.append({
            "id": thought.get("id"),
            "name": thought.get("name", "未命名思维"),
            "progress": thought.get("progress", 0),
            "required_progress": thought.get("required_progress", 0),
            "progress_cues": [str(cue) for cue in cues],
            "latest_progress_note": latest_note,
        })
    return active


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Disco 主动与被动检定工具")
    parser.add_argument("command", choices=("passive", "active", "passive-batch"))
    parser.add_argument("--skill")
    parser.add_argument("--dc", type=int)
    parser.add_argument("--condition", action="append", default=[])
    parser.add_argument("--modifier", action="append", default=[])
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET_PATH)
    parser.add_argument("--thoughts", type=Path, default=DEFAULT_THOUGHT_PATH)
    parser.add_argument("--request-json")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--no-log", action="store_true")
    return parser


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run_single(args: argparse.Namespace) -> dict[str, Any]:
    if not args.skill or args.dc is None:
        raise CheckError(f"{args.command} requires --skill and --dc")
    dc = normalize_dc(args.dc)
    skill = skill_context(args.skill, args.sheet, args.thoughts, args.condition)
    situational = parse_situational_modifiers(args.modifier)
    if args.command == "passive":
        return passive_check(skill, dc, situational)
    result = active_check(skill, dc, situational)
    if not args.no_log:
        write_log(result, args.log)
    return result


def run_passive_batch(args: argparse.Namespace) -> dict[str, Any]:
    if not args.request_json:
        raise CheckError("passive-batch requires --request-json")
    try:
        request = json.loads(args.request_json)
    except json.JSONDecodeError as exc:
        raise CheckError("request JSON is invalid") from exc
    checks = request.get("checks")
    if not isinstance(checks, list):
        raise CheckError("request JSON must contain a checks list")
    sheet = load_sheet(args.sheet)
    thoughts = load_yaml(args.thoughts)
    results = []
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("skill"), str):
            raise CheckError("each passive check needs a skill and integer or difficulty-label dc")
        dc = normalize_dc(item.get("dc"))
        conditions = item.get("conditions", [])
        modifiers = item.get("modifiers", [])
        if not isinstance(conditions, list) or not isinstance(modifiers, list):
            raise CheckError("conditions and modifiers must be lists")
        skill = calculate_effective_skill(sheet, thoughts, item["skill"], set(conditions))
        situational = parse_situational_modifiers(modifiers)
        results.append(passive_check(skill, dc, situational))
    return {
        "mode": "passive-batch",
        "checks": results,
        "thought_audit": active_thought_audit(thoughts),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_passive_batch(args) if args.command == "passive-batch" else run_single(args)
        emit(result)
        return 0
    except (CheckError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
