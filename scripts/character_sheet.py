from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

ATTRIBUTES = ("智力", "精神", "体格", "身手")
CANONICAL_PERSONALITIES = (
    "逻辑思维", "博学多闻", "能说会道", "故弄玄虚", "标新立异", "见微知著",
    "平心定气", "内陆帝国", "通情达理", "争强好胜", "同舟共济", "循循善诱",
    "钢筋铁骨", "坚忍不拔", "强身健体", "食髓知味", "天人感应", "疑神疑鬼",
    "眼明手巧", "五感发达", "反应速度", "鬼祟玲珑", "能工巧匠", "从容自若",
)
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()
DEFAULT_STATE_DIR = DEFAULT_CODEX_HOME / "state" / "disco-elysium-personalities"
DEFAULT_SHEET_PATH = DEFAULT_STATE_DIR / "character-sheet.yaml"
DEFAULT_THOUGHT_PATH = DEFAULT_STATE_DIR / "thought-cabinet.yaml"
DIRECT_EFFECT = re.compile(r"^([+-]\d+)\s+(.+)$")
CONDITIONAL_EFFECT = re.compile(r"^(.+?)的(.+?)检定\s+([+-]\d+)$")


class CharacterSheetError(ValueError):
    """Raised when a character or thought state cannot be trusted."""


def validate_sheet_data(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("version") != 1:
        raise CharacterSheetError("version must be 1")
    if data.get("onboarding_status") != "confirmed":
        raise CharacterSheetError("onboarding_status must be confirmed")
    attributes = data.get("attributes")
    if not isinstance(attributes, dict) or set(attributes) != set(ATTRIBUTES):
        raise CharacterSheetError("attributes must contain the four canonical attributes")
    if any(not isinstance(value, int) or not 1 <= value <= 6 for value in attributes.values()):
        raise CharacterSheetError("attribute values must be between 1 and 6")
    if sum(attributes.values()) != 12:
        raise CharacterSheetError("attribute values must sum to 12")
    if data.get("signature_skill") not in CANONICAL_PERSONALITIES:
        raise CharacterSheetError("signature_skill must be canonical")
    skills = data.get("base_skills")
    if not isinstance(skills, dict) or set(skills) != set(CANONICAL_PERSONALITIES):
        raise CharacterSheetError("base_skills must contain only the 24 canonical personalities")
    if any(not isinstance(value, int) or value < 1 for value in skills.values()):
        raise CharacterSheetError("base skill values must be positive integers")
    if not isinstance(data.get("confirmed_at"), str) or not data["confirmed_at"].strip():
        raise CharacterSheetError("confirmed_at must be a non-empty string")
    return data


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CharacterSheetError(f"state file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CharacterSheetError(f"cannot read YAML state: {path}") from exc
    if not isinstance(data, dict):
        raise CharacterSheetError(f"YAML root must be a mapping: {path}")
    return data


def load_sheet(path: Path = DEFAULT_SHEET_PATH) -> dict[str, Any]:
    return validate_sheet_data(load_yaml(path))


def install_sheet(input_path: Path, output_path: Path = DEFAULT_SHEET_PATH) -> Path:
    data = validate_sheet_data(load_yaml(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = output_path.parent / "backups" / f"{stamp}-character-sheet.yaml"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, backup)
    rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    candidate = output_path.with_suffix(output_path.suffix + ".validated")
    candidate.write_text(rendered, encoding="utf-8")
    validate_sheet_data(load_yaml(candidate))
    shutil.copy2(candidate, output_path)
    return output_path


def active_effects(thought: dict[str, Any]) -> Iterable[str]:
    status = thought.get("status")
    if status == "研究中":
        return thought.get("temporary_research_bonus", []) or []
    if status == "已内在化":
        return thought.get("completion_effect", []) or []
    return []


def effect_for_skill(effect: str, skill: str, conditions: set[str]) -> int | None:
    direct = DIRECT_EFFECT.fullmatch(effect.strip())
    if direct and direct.group(2) == skill:
        return int(direct.group(1))
    conditional = CONDITIONAL_EFFECT.fullmatch(effect.strip())
    if conditional and conditional.group(2) == skill and conditional.group(1) in conditions:
        return int(conditional.group(3))
    return None


def calculate_effective_skill(
    sheet: dict[str, Any],
    thought_state: dict[str, Any],
    skill: str,
    conditions: set[str] | None = None,
) -> dict[str, Any]:
    validate_sheet_data(sheet)
    if skill not in CANONICAL_PERSONALITIES:
        raise CharacterSheetError(f"unknown canonical skill: {skill}")
    conditions = conditions or set()
    breakdown: list[dict[str, Any]] = []
    for thought in thought_state.get("thoughts", []):
        for effect in active_effects(thought):
            value = effect_for_skill(str(effect), skill, conditions)
            if value is not None:
                breakdown.append({
                    "source": thought.get("name", "未命名思维"),
                    "status": thought.get("status"),
                    "effect": str(effect),
                    "value": value,
                })
    base = sheet["base_skills"][skill]
    thought_total = sum(item["value"] for item in breakdown)
    return {
        "skill": skill,
        "base": base,
        "thought_modifiers": breakdown,
        "thought_total": thought_total,
        "effective": base + thought_total,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Disco 人物卡与思维修正工具")
    parser.add_argument("command", choices=("status", "validate", "effective", "install"))
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET_PATH)
    parser.add_argument("--thoughts", type=Path, default=DEFAULT_THOUGHT_PATH)
    parser.add_argument("--skill")
    parser.add_argument("--condition", action="append", default=[])
    parser.add_argument("--input", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "install":
            if args.input is None:
                raise CharacterSheetError("install requires --input")
            output = install_sheet(args.input, args.sheet)
            emit({"installed": True, "path": str(output)})
            return 0

        sheet = load_sheet(args.sheet)
        if args.command == "validate":
            emit({"valid": True, "path": str(args.sheet)})
            return 0
        if args.command == "status":
            emit(sheet)
            return 0
        if not args.skill:
            raise CharacterSheetError("effective requires --skill")
        thoughts = load_yaml(args.thoughts)
        emit(calculate_effective_skill(sheet, thoughts, args.skill, set(args.condition)))
        return 0
    except (CharacterSheetError, OSError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
