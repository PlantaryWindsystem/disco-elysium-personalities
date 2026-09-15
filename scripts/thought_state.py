from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

import yaml


VALID_STATUSES = ("已获得", "研究中", "已内在化")
TRANSITIONS = {
    ("已获得", "研究中"),
    ("研究中", "已内在化"),
}


class ThoughtStateError(ValueError):
    """Raised when a thought-cabinet operation would make state ambiguous."""


def empty_state() -> dict[str, Any]:
    return {"version": 1, "thoughts": []}


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ThoughtStateError("thought cabinet version must be 1")
    thoughts = state.get("thoughts")
    if not isinstance(thoughts, list):
        raise ThoughtStateError("thought cabinet must contain a thoughts list")

    ids: set[str] = set()
    for thought in thoughts:
        if not isinstance(thought, dict):
            raise ThoughtStateError("each thought must be an object")
        thought_id = thought.get("id")
        if not isinstance(thought_id, str) or not thought_id.strip():
            raise ThoughtStateError("each thought needs a non-empty id")
        if thought_id in ids:
            raise ThoughtStateError(f"duplicate thought id: {thought_id}")
        ids.add(thought_id)

        status = thought.get("status", "已获得")
        if status not in VALID_STATUSES:
            raise ThoughtStateError(f"unsupported thought status: {status}")
        progress = thought.get("progress", 0)
        required = thought.get("required_progress", 1)
        if not isinstance(progress, int) or progress < 0:
            raise ThoughtStateError(f"invalid progress for thought: {thought_id}")
        if not isinstance(required, int) or required < 1 or progress > required:
            raise ThoughtStateError(f"invalid required progress for thought: {thought_id}")
        log = thought.get("progress_log", [])
        if not isinstance(log, list):
            raise ThoughtStateError(f"progress_log must be a list: {thought_id}")
    return deepcopy(state)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ThoughtStateError(f"cannot read thought cabinet: {path}") from exc
    return validate_state(raw if raw is not None else empty_state())


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _find(state: dict[str, Any], thought_id: str) -> dict[str, Any]:
    for thought in state["thoughts"]:
        if thought["id"] == thought_id:
            return thought
    raise ThoughtStateError(f"thought not found: {thought_id}")


def _write_state(path: Path, state: dict[str, Any], backup_dir: Path | None) -> None:
    validated = validate_state(state)
    if path.exists():
        destination = backup_dir or path.parent / "backups"
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, destination / f"{path.stem}-{stamp}{path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(validated, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def apply_operation(
    path: Path,
    operation: str,
    *,
    thought: dict[str, Any] | None = None,
    thought_id: str | None = None,
    steps: int = 1,
    note: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply one explicit thought-cabinet operation and verify the saved state."""
    before = load_state(path)
    before_ids = [item["id"] for item in before["thoughts"]]
    state = deepcopy(before)
    idempotent = False

    if operation == "validate":
        validate_state(state)
        return {"verified": True, "thoughts": state["thoughts"]}

    if operation == "acquire":
        if not isinstance(thought, dict):
            raise ThoughtStateError("acquire requires a thought object")
        candidate = validate_state({"version": 1, "thoughts": [thought]})["thoughts"][0]
        existing = next((item for item in state["thoughts"] if item["id"] == candidate["id"]), None)
        if existing is not None:
            if existing != candidate:
                raise ThoughtStateError(f"thought id already contains different data: {candidate['id']}")
            idempotent = True
        else:
            state["thoughts"].append(candidate)
    else:
        if not isinstance(thought_id, str) or not thought_id.strip():
            raise ThoughtStateError(f"{operation} requires thought_id")
        target = _find(state, thought_id)
        now = _now()
        if operation == "place":
            target.setdefault("placed_at", now)
        elif operation == "start_research":
            if target["status"] == "研究中":
                idempotent = True
            elif (target["status"], "研究中") not in TRANSITIONS:
                raise ThoughtStateError(f"cannot start research from {target['status']}")
            else:
                target["status"] = "研究中"
                target.setdefault("started_at", now)
        elif operation == "progress":
            if target["status"] != "研究中":
                raise ThoughtStateError("progress requires a thought in research")
            if not isinstance(steps, int) or steps < 1:
                raise ThoughtStateError("steps must be a positive integer")
            target["progress"] = min(target["required_progress"], target["progress"] + steps)
            entry = {"step": target["progress"], "recorded_at": now}
            if note:
                entry["note"] = note
            target.setdefault("progress_log", []).append(entry)
        elif operation == "internalize":
            if target["status"] == "已内在化":
                idempotent = True
            elif target["status"] != "研究中" or target["progress"] < target["required_progress"]:
                raise ThoughtStateError("internalize requires completed research")
            else:
                target["status"] = "已内在化"
                target["completed_at"] = now
        else:
            raise ThoughtStateError(f"unsupported thought operation: {operation}")

    _write_state(path, state, backup_dir)
    saved = load_state(path)
    saved_ids = [item["id"] for item in saved["thoughts"]]
    if saved_ids[:len(before_ids)] != before_ids:
        raise ThoughtStateError("thought cabinet verification lost an existing thought")
    result_thought = None
    if thought_id:
        result_thought = _find(saved, thought_id)
    elif isinstance(thought, dict):
        result_thought = _find(saved, thought["id"])
    return {
        "verified": True,
        "idempotent": idempotent,
        "thought": result_thought,
        "thoughts": saved["thoughts"],
    }
