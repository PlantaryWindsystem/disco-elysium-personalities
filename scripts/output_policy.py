from __future__ import annotations

from typing import Any


FAILURE_TYPES = {
    "silent",
    "misread",
    "reverse_passive",
    "impulse",
    "relational_crack",
}
SPECIAL_FUNCTIONS = {
    "atmosphere",
    "existential",
    "sensory_body",
    "bottom_impulse",
}


def failure_type(value: Any, *, surface: bool) -> str:
    if not surface or value not in FAILURE_TYPES or value == "silent":
        return "silent"
    return value


def select_visible_candidates(
    candidates: list[dict[str, Any]],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Keep only voices that add content or a meaningful, surfaced failure."""
    if limit < 1:
        return []
    visible: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        if item.get("success"):
            if not item.get("contribution"):
                continue
            item["failure_type"] = None
        else:
            item["failure_type"] = failure_type(
                item.get("failure_type"),
                surface=bool(item.get("surface")),
            )
            if item["failure_type"] == "silent":
                continue
        visible.append(item)
    visible.sort(key=lambda item: item.get("priority", 0), reverse=True)
    return visible[:limit]


def select_visible_special_voices(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Special voices can surface for atmosphere without a personality-style check."""
    visible: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        if not item.get("surface"):
            continue
        if item.get("function") not in SPECIAL_FUNCTIONS:
            continue
        visible.append(item)
    return visible
