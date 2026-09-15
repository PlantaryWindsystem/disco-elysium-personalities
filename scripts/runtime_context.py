from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from character_sheet import (
    CANONICAL_PERSONALITIES,
    DEFAULT_SHEET_PATH,
    DEFAULT_THOUGHT_PATH,
    calculate_effective_skill,
    load_sheet,
    load_yaml,
)
from check_engine import (
    active_thought_audit,
    normalize_dc,
    parse_situational_modifiers,
    passive_check,
)
from output_policy import select_visible_candidates, select_visible_special_voices
from thought_state import apply_operation as apply_thought_operation

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_DIR = SKILL_ROOT / "references"
DEFAULT_INDEX_PATH = DEFAULT_REFERENCE_DIR / "运行时人格索引.json"
DEFAULT_THOUGHT_TRIGGER_PATH = DEFAULT_THOUGHT_PATH.with_name("thought-trigger-state.yaml")

ATTRIBUTE_GROUPS = {
    "智力": CANONICAL_PERSONALITIES[0:6],
    "精神": CANONICAL_PERSONALITIES[6:12],
    "体格": CANONICAL_PERSONALITIES[12:18],
    "身手": CANONICAL_PERSONALITIES[18:24],
}
ATTRIBUTE_COLORS = {"智力": "🟦", "精神": "🟪", "体格": "🟥", "身手": "🟨"}
PERSONALITY_ATTRIBUTES = {
    name: attribute
    for attribute, names in ATTRIBUTE_GROUPS.items()
    for name in names
}
SPECIAL_VOICES = ("古老的爬虫脑", "边缘系统", "脊髓")
RUNTIME_MODES = {"minimal", "standard", "deep"}
DERIVED_FIELDS = {
    "核心动作": "core_action",
    "成功写法": "success",
    "失败写法": "failure",
    "句法节奏": "rhythm",
    "边界": "boundary",
}
PROFILE_RUNTIME_FIELDS = (
    "name",
    "attribute",
    "color",
    "core_action",
    "success",
    "failure",
    "rhythm",
    "boundary",
    "samples",
    "reference",
)


class RuntimeContextError(ValueError):
    """Raised when compact runtime context cannot be built without guessing."""


def resolve_runtime_mode(request: dict[str, Any]) -> str:
    value = request.get("runtime_mode", "standard")
    return value if isinstance(value, str) and value in RUNTIME_MODES else "standard"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_derived_fields(text: str, name: str) -> dict[str, str]:
    match = re.search(
        r"<!-- director-cut-derived:start -->(.*?)<!-- director-cut-derived:end -->",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise RuntimeContextError(f"{name} lacks director-cut-derived markers")
    block = match.group(1)
    result: dict[str, str] = {}
    for label, key in DERIVED_FIELDS.items():
        field = re.search(rf"^- \*\*{re.escape(label)}\*\*：(.+)$", block, flags=re.MULTILINE)
        if field is None or not field.group(1).strip():
            raise RuntimeContextError(f"{name} lacks derived field: {label}")
        result[key] = field.group(1).strip()
    return result


def sample_lines(block: str, marker: str, limit: int) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith(("```", "#", "- ")):
            continue
        line = re.sub(r"^【(?:成功|失败)】", "", line).strip()
        if not 8 <= len(line) <= 180:
            continue
        samples.append({"kind": marker, "text": line})
        if len(samples) == limit:
            break
    return samples


def extract_samples(text: str, name: str) -> list[dict[str, str]]:
    success = re.search(r"## 含成功\s*(.*?)### 不含成功", text, flags=re.DOTALL)
    failure = re.search(r"### 不含成功\s*(.*?)```", text, flags=re.DOTALL)
    if success is None or failure is None:
        raise RuntimeContextError(f"{name} lacks success/failure sample sections")
    samples = sample_lines(success.group(1), "成功", 2)
    samples.extend(sample_lines(failure.group(1), "失败", 1))
    if len(samples) < 2:
        raise RuntimeContextError(f"{name} does not provide enough compact samples")
    return samples


def section_between(text: str, start: str, end_pattern: str) -> str:
    match = re.search(
        rf"^### {re.escape(start)}\s*(.*?)(?=^### (?:{end_pattern})\s*$|\Z)",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise RuntimeContextError(f"special voice lacks section: {start}")
    return match.group(1).strip()


def compact_paragraph(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(line[2:] if line.startswith("- ") else line for line in lines)


def extract_special_voice(text: str, name: str, source_hash: str) -> dict[str, Any]:
    section = re.search(
        rf"^## {re.escape(name)}\s*(.*?)(?=^## (?:{'|'.join(map(re.escape, SPECIAL_VOICES))}|自动路由)\s*$|\Z)",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if section is None:
        raise RuntimeContextError(f"special voice is missing: {name}")
    body = section.group(1)
    return {
        "name": name,
        "color": "⬛",
        "core": compact_paragraph(section_between(body, "核心", "触发|写法")),
        "triggers": compact_paragraph(section_between(body, "触发", "核心|写法")),
        "style": compact_paragraph(section_between(body, "写法", "核心|触发")),
        "reference": "references/特殊脑内声音.md",
        "source_sha256": source_hash,
    }


def build_runtime_index(reference_dir: Path = DEFAULT_REFERENCE_DIR) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}
    for name in CANONICAL_PERSONALITIES:
        path = reference_dir / f"{name}.md"
        if not path.is_file():
            raise RuntimeContextError(f"personality reference is missing: {path}")
        text = path.read_text(encoding="utf-8")
        attribute = PERSONALITY_ATTRIBUTES[name]
        profile: dict[str, Any] = {
            "name": name,
            "attribute": attribute,
            "color": ATTRIBUTE_COLORS[attribute],
        }
        profile.update(extract_derived_fields(text, name))
        profile.update({
            "samples": extract_samples(text, name),
            "reference": f"references/{name}.md",
            "source_sha256": sha256_text(text),
        })
        profiles[name] = profile

    special_path = reference_dir / "特殊脑内声音.md"
    if not special_path.is_file():
        raise RuntimeContextError(f"special voice reference is missing: {special_path}")
    special_text = special_path.read_text(encoding="utf-8")
    special_hash = sha256_text(special_text)
    special_voices = {
        name: extract_special_voice(special_text, name, special_hash)
        for name in SPECIAL_VOICES
    }
    return {
        "version": 1,
        "generated_from": "references/*人格.md 的导演剪辑版归纳与短语料；特殊脑内声音.md",
        "profiles": profiles,
        "special_voices": special_voices,
    }


def write_runtime_index(
    output: Path = DEFAULT_INDEX_PATH,
    reference_dir: Path = DEFAULT_REFERENCE_DIR,
    replace: bool = False,
) -> Path:
    payload = build_runtime_index(reference_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing index: {output}")
    if output.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = SKILL_ROOT / "backups" / f"{stamp}-runtime-index" / output.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, backup)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def load_runtime_index(path: Path = DEFAULT_INDEX_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeContextError(f"runtime index is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeContextError(f"cannot read runtime index: {path}") from exc
    if payload.get("version") != 1:
        raise RuntimeContextError("runtime index version must be 1")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(CANONICAL_PERSONALITIES):
        raise RuntimeContextError("runtime index must contain the 24 canonical personalities")
    voices = payload.get("special_voices")
    if not isinstance(voices, dict) or set(voices) != set(SPECIAL_VOICES):
        raise RuntimeContextError("runtime index must contain the three special voices")
    return payload


def selected_names(request: dict[str, Any], field: str, allowed: tuple[str, ...]) -> list[str]:
    names = request.get(field, [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise RuntimeContextError(f"{field} must be a list of names")
    if len(names) != len(set(names)):
        raise RuntimeContextError(f"{field} contains duplicate names")
    unknown = [name for name in names if name not in allowed]
    if unknown:
        raise RuntimeContextError(f"unknown names in {field}: {', '.join(unknown)}")
    return names


def compact_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {field: profile[field] for field in PROFILE_RUNTIME_FIELDS}


def thought_ids_fingerprint(thoughts: dict[str, Any]) -> str:
    entries = thoughts.get("thoughts", [])
    if not isinstance(entries, list):
        raise RuntimeContextError("thoughts must contain a list")
    ids = sorted({
        item["id"].strip()
        for item in entries
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    })
    return sha256_text("\n".join(ids))


def due_turn_for(fingerprint: str) -> int:
    seed = sha256_text(f"thought-trigger:{fingerprint}")
    return 15 + int(seed[:8], 16) % 11


def load_thought_trigger_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        state = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeContextError(f"cannot read thought trigger state: {path}") from exc
    if not isinstance(state, dict) or state.get("version") != 1:
        raise RuntimeContextError("thought trigger state version must be 1")
    return state


def thought_trigger_status(turns: int, due_turn: int) -> str:
    if turns >= due_turn:
        return "due"
    if turns >= 10:
        return "heightened"
    return "normal"


def assess_thought_candidate(
    candidate: dict[str, Any] | None,
    thoughts: dict[str, Any],
) -> dict[str, Any]:
    """Gate a due reminder without turning a timer into an automatic popup."""
    if not isinstance(candidate, dict):
        return {"eligible": False, "reason": "no-candidate"}
    required = ("id", "name", "source", "mechanism", "problem", "acquisition")
    missing = [field for field in required if not isinstance(candidate.get(field), str) or not candidate[field].strip()]
    if missing:
        return {"eligible": False, "reason": "missing-fields", "missing": missing}
    existing_ids = {
        item.get("id")
        for item in thoughts.get("thoughts", [])
        if isinstance(item, dict)
    }
    if candidate["id"] in existing_ids:
        return {"eligible": False, "reason": "duplicate-id"}
    mechanism = candidate["mechanism"].strip()
    if len(mechanism) < 8:
        return {"eligible": False, "reason": "mechanism-too-thin"}
    return {"eligible": True, "reason": "mature-candidate"}


def assess_thought_review(review: dict[str, Any] | None) -> dict[str, Any]:
    """Validate an explicit semantic review when a due trigger has no mature candidate."""
    if not isinstance(review, dict):
        return {"valid": False, "reason": "no-review"}
    if review.get("result") != "no-mature-candidate":
        return {"valid": False, "reason": "invalid-review-result"}
    reason = review.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 8:
        return {"valid": False, "reason": "review-reason-too-thin"}
    return {
        "valid": True,
        "reason": "reviewed-no-mature-candidate",
        "detail": reason.strip(),
    }


def update_thought_trigger_state(
    thoughts: dict[str, Any],
    path: Path,
    turn_key: str | None,
    substantive: bool,
    candidate: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint = thought_ids_fingerprint(thoughts)
    state = load_thought_trigger_state(path)
    changed = state is None or state.get("thought_ids_fingerprint") != fingerprint
    if changed:
        state = {
            "version": 1,
            "thought_ids_fingerprint": fingerprint,
            "turns_since_new_thought": 0,
            "next_due_turn": due_turn_for(fingerprint),
            "last_substantive_turn_hash": None,
            "last_candidate_review_turn": None,
            "review_deferred_until": None,
        }

    assert state is not None
    turns = state.get("turns_since_new_thought")
    due_turn = state.get("next_due_turn")
    if not isinstance(turns, int) or turns < 0:
        raise RuntimeContextError("thought trigger turn count must be a non-negative integer")
    if not isinstance(due_turn, int) or not 15 <= due_turn <= 25:
        raise RuntimeContextError("thought trigger due turn must be between 15 and 25")
    deferred_until = state.get("review_deferred_until")
    if deferred_until is not None and (not isinstance(deferred_until, int) or deferred_until < 0):
        raise RuntimeContextError("thought trigger review deferral must be a non-negative integer")

    counted = False
    normalized_key = turn_key.strip() if isinstance(turn_key, str) else ""
    if substantive and normalized_key:
        turn_hash = sha256_text(normalized_key)
        if turn_hash != state.get("last_substantive_turn_hash"):
            turns += 1
            state["turns_since_new_thought"] = turns
            state["last_substantive_turn_hash"] = turn_hash
            counted = True

    status = thought_trigger_status(turns, due_turn)
    candidate_gate = assess_thought_candidate(candidate, thoughts)
    review_gate = assess_thought_review(review)
    reviewed = False
    if status == "due" and substantive and not candidate_gate["eligible"] and review_gate["valid"]:
        state["last_candidate_review_turn"] = turns
        state["review_deferred_until"] = turns + 3
        deferred_until = turns + 3
        reviewed = True

    if changed or counted or reviewed:
        state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(state, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    review_required = (
        status == "due"
        and substantive
        and not candidate_gate["eligible"]
        and (deferred_until is None or turns >= deferred_until)
    )
    return {
        "turns_since_new_thought": turns,
        "next_due_turn": due_turn,
        "status": status,
        "overdue_by": max(0, turns - due_turn),
        "should_unlock": status == "due" and substantive and candidate_gate["eligible"],
        "candidate_ready": candidate_gate["eligible"],
        "candidate_gate": candidate_gate,
        "review_required": review_required,
        "review_deferred_until": deferred_until,
        "candidate_review": review_gate,
        "counted": counted,
    }


def build_runtime_payload(
    request: dict[str, Any],
    index_path: Path = DEFAULT_INDEX_PATH,
    sheet_path: Path = DEFAULT_SHEET_PATH,
    thoughts_path: Path = DEFAULT_THOUGHT_PATH,
    trigger_path: Path = DEFAULT_THOUGHT_TRIGGER_PATH,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise RuntimeContextError("request JSON root must be an object")
    profile_names = selected_names(request, "profiles", CANONICAL_PERSONALITIES)
    voice_names = selected_names(request, "special_voices", SPECIAL_VOICES)
    mode = resolve_runtime_mode(request)
    checks = request.get("checks", [])
    if not isinstance(checks, list):
        raise RuntimeContextError("checks must be a list")
    turn_key = request.get("turn_key")
    if turn_key is not None and (not isinstance(turn_key, str) or not turn_key.strip()):
        raise RuntimeContextError("turn_key must be a non-empty string when provided")
    substantive = request.get("substantive", True)
    if not isinstance(substantive, bool):
        raise RuntimeContextError("substantive must be a boolean")
    candidate_attributes = request.get("candidate_attributes")
    if candidate_attributes is None:
        candidate_attributes = list(dict.fromkeys(
            PERSONALITY_ATTRIBUTES[name] for name in profile_names
        ))
    if (
        not isinstance(candidate_attributes, list)
        or any(item not in ATTRIBUTE_GROUPS for item in candidate_attributes)
    ):
        raise RuntimeContextError("candidate_attributes must be a list of canonical attributes")
    candidate_attributes = list(dict.fromkeys(candidate_attributes))

    index = load_runtime_index(index_path)
    payload = {
        "mode": "runtime-context",
        "runtime_mode": mode,
        "profiles": [compact_profile(index["profiles"][name]) for name in profile_names],
        "special_voices": [index["special_voices"][name] for name in voice_names],
        "checks": [],
        "candidate_attributes": candidate_attributes,
    }
    if mode == "minimal":
        if checks:
            raise RuntimeContextError("minimal runtime mode does not run checks")
        return payload

    sheet = load_sheet(sheet_path) if checks else None
    thoughts = load_yaml(thoughts_path)
    check_results: list[dict[str, Any]] = []
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("skill"), str):
            raise RuntimeContextError("each passive check needs a skill and integer or difficulty-label dc")
        dc = normalize_dc(item.get("dc"))
        conditions = item.get("conditions", [])
        modifiers = item.get("modifiers", [])
        if not isinstance(conditions, list) or not isinstance(modifiers, list):
            raise RuntimeContextError("conditions and modifiers must be lists")
        if sheet is None:
            raise RuntimeContextError("sheet is required when checks are present")
        skill = calculate_effective_skill(sheet, thoughts, item["skill"], set(conditions))
        check_results.append(passive_check(skill, dc, parse_situational_modifiers(modifiers)))

    payload["checks"] = check_results
    payload["thought_audit"] = active_thought_audit(thoughts)
    payload["thought_trigger"] = update_thought_trigger_state(
        thoughts,
        trigger_path,
        turn_key,
        substantive,
        request.get("thought_candidate"),
        request.get("thought_review"),
    )
    return payload


def parse_request(raw: str | None) -> dict[str, Any]:
    if raw is None:
        raise RuntimeContextError("context requires --request-json")
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeContextError("request JSON is invalid") from exc
    if not isinstance(request, dict):
        raise RuntimeContextError("request JSON root must be an object")
    return request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Disco 紧凑人格、检定与思维上下文工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-index")
    build.add_argument("--references", type=Path, default=DEFAULT_REFERENCE_DIR)
    build.add_argument("--output", type=Path, default=DEFAULT_INDEX_PATH)
    build.add_argument("--replace", action="store_true")

    context = subparsers.add_parser("context")
    context.add_argument("--request-json", required=True)
    context.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    context.add_argument("--sheet", type=Path, default=DEFAULT_SHEET_PATH)
    context.add_argument("--thoughts", type=Path, default=DEFAULT_THOUGHT_PATH)
    context.add_argument("--thought-trigger", type=Path, default=DEFAULT_THOUGHT_TRIGGER_PATH)

    thought = subparsers.add_parser("thought")
    thought.add_argument("--path", type=Path, default=DEFAULT_THOUGHT_PATH)
    thought.add_argument("--operation", required=True, choices=(
        "validate", "acquire", "place", "start_research", "progress", "internalize",
    ))
    thought.add_argument("--thought-json")
    thought.add_argument("--thought-id")
    thought.add_argument("--steps", type=int, default=1)
    thought.add_argument("--note")
    thought.add_argument("--backup-dir", type=Path)
    return parser


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build-index":
            path = write_runtime_index(args.output, args.references, args.replace)
            emit({"built": True, "path": str(path)})
            return 0
        if args.command == "thought":
            thought = None
            if args.thought_json:
                try:
                    thought = json.loads(args.thought_json)
                except json.JSONDecodeError as exc:
                    raise RuntimeContextError("thought JSON is invalid") from exc
            emit(apply_thought_operation(
                args.path,
                args.operation,
                thought=thought,
                thought_id=args.thought_id,
                steps=args.steps,
                note=args.note,
                backup_dir=args.backup_dir,
            ))
            return 0
        request = parse_request(args.request_json)
        emit(build_runtime_payload(
            request,
            args.index,
            args.sheet,
            args.thoughts,
            args.thought_trigger,
        ))
        return 0
    except (RuntimeContextError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
