from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


COLOR_BY_ATTRIBUTE = {
    "智力": "🟦",
    "精神": "🟪",
    "体格": "🟥",
    "身手": "🟨",
}

PERSONALITY_ATTRIBUTE = {
    "逻辑思维": "智力", "博学多闻": "智力", "能说会道": "智力",
    "故弄玄虚": "智力", "标新立异": "智力", "见微知著": "智力",
    "平心定气": "精神", "内陆帝国": "精神", "通情达理": "精神",
    "争强好胜": "精神", "同舟共济": "精神", "循循善诱": "精神",
    "钢筋铁骨": "体格", "坚忍不拔": "体格", "强身健体": "体格",
    "食髓知味": "体格", "天人感应": "体格", "疑神疑鬼": "体格",
    "眼明手巧": "身手", "五感发达": "身手", "反应速度": "身手",
    "鬼祟玲珑": "身手", "能工巧匠": "身手", "从容自若": "身手",
}
DIFFICULTIES = "极易|容易|中等|挑战|困难|极难|专家|噩梦|炼狱"
RESULTS = "成功|失败"
PERSONALITIES = "|".join(sorted(PERSONALITY_ATTRIBUTE, key=len, reverse=True))
PERSONALITY_HEADING = re.compile(
    rf"^> (?P<color>[🟦🟪🟥🟨]) \*\*(?P<name>{PERSONALITIES})(?P<sense>（(?:视觉|听觉|嗅觉|触觉|味觉)）)?"
    rf"【(?P<difficulty>{DIFFICULTIES})：(?P<result>{RESULTS})】\*\*$"
)
SPECIAL_HEADING = re.compile(r"^> ⬛ \*\*(?:古老的爬虫脑|边缘系统|脊髓)\*\*$")
BAD_BOLD_HEADING = re.compile(r"^>\s+\*\*(?:" + PERSONALITIES + r").*$")
PERSONALITY_LIKE_HEADING = re.compile(
    r"^>\s*(?:[🟦🟪🟥🟨]\s*)?\*{0,2}(?:" + PERSONALITIES + r").*"
)
FORBIDDEN_CONTRAST = re.compile(r"不是[^\n]{0,120}而是")
LIST_ITEM = re.compile(r"^>\s+(?:[-+*]|\d+[.)])\s+")
COUNSELING_PANEL_PATTERNS = (
    re.compile(r"你这句[^\n]{0,28}(?:是在说|意味着)"),
    re.compile(r"你的(?:感受|无力感|痛苦)[^\n]{0,28}(?:准确|真实|合理)"),
    re.compile(r"(?:所以|因此)[^\n]{0,32}(?:先|可以|不必|不用)"),
    re.compile(r"我知道"),
    re.compile(r"我会[^\n]{0,20}(?:陪|和你)"),
    re.compile(r"这就是[^\n]{0,24}(?:不公平|痛苦|无力)"),
    re.compile(r"它缺的是"),
    re.compile(r"你确实没有办法"),
)
VOICE_TEXTURE = re.compile(
    r"[？！!?…]|\*[^*]+\*|(?:^|[。！？!?…])\s*(?:啊|很好|正确|显然|也许|停下|看|听|别|快|马上|咔哒|砰|再说一次)"
)
THOUGHT_TITLE = re.compile(
    r"^> \*\*(?P<name>(?!获得思维：).+?)（(?P<source>Earth|Elysium)）\*\*$"
)
THOUGHT_ACQUISITION_TITLE = re.compile(
    r"^> \*\*获得思维：(?P<name>.+?)（(?P<source>Earth|Elysium)）\*\*$"
)
THOUGHT_ACQUISITION_OPTIONS = re.compile(
    r"^> \[内在化\][ \t　]+\[放入思维阁\]$"
)
THOUGHT_FIELD = re.compile(
    r"^> \*\*(?P<label>临时研究加成|研究完成效果|研究时间|获取方式|问题|解答)：\*\* (?P<content>.+)$"
)
RESEARCH_THOUGHT_FIELDS = ("临时研究加成", "研究时间", "获取方式", "问题")
INTERNALIZED_THOUGHT_FIELDS = ("研究完成效果", "研究时间", "获取方式", "问题", "解答")
MIN_EARTH_THOUGHT_PROSE = 120


def _extract_personality_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = PERSONALITY_HEADING.fullmatch(line)
        if match:
            if current is not None:
                current["body"] = "\n".join(current.pop("lines")).strip()
                blocks.append(current)
            name = match.group("name")
            current = {
                "name": name,
                "attribute": PERSONALITY_ATTRIBUTE[name],
                "lines": [],
            }
            continue
        if SPECIAL_HEADING.fullmatch(line):
            if current is not None:
                current["body"] = "\n".join(current.pop("lines")).strip()
                blocks.append(current)
                current = None
            continue
        if (
            THOUGHT_TITLE.fullmatch(line)
            or THOUGHT_ACQUISITION_TITLE.fullmatch(line)
            or THOUGHT_FIELD.fullmatch(line)
            or THOUGHT_ACQUISITION_OPTIONS.fullmatch(line)
        ):
            if current is not None:
                current["body"] = "\n".join(current.pop("lines")).strip()
                blocks.append(current)
                current = None
            continue
        if current is None:
            continue
        if line.startswith(">"):
            content = line[1:].lstrip()
            if content:
                current["lines"].append(content)
        elif line.strip():
            current["body"] = "\n".join(current.pop("lines")).strip()
            blocks.append(current)
            current = None
    if current is not None:
        current["body"] = "\n".join(current.pop("lines")).strip()
        blocks.append(current)
    return blocks


def _validate_ensemble_fidelity(blocks: list[dict[str, str]]) -> list[str]:
    """Reject the narrow failure mode where headings mask one uniform counseling voice."""
    if len(blocks) < 3:
        return []
    bodies = [block["body"] for block in blocks if block["body"]]
    if len(bodies) < 3:
        return []
    lengths = [len(body) for body in bodies]
    if min(lengths) < 45 or max(lengths) / max(1, min(lengths)) > 2.2:
        return []
    counseling_hits = sum(
        len(pattern.findall(body))
        for body in bodies
        for pattern in COUNSELING_PANEL_PATTERNS
    )
    textured_blocks = sum(bool(VOICE_TEXTURE.search(body)) for body in bodies)
    if counseling_hits >= len(bodies) and textured_blocks <= 1:
        return [
            "generic counseling panel: personality headings cover uniformly paced counseling prose; "
            "restore distinct thought actions, uneven rhythm, and voice-specific failure modes"
        ]
    return []


def _validate_voice_block_rhythm(text: str) -> list[str]:
    errors: list[str] = []
    active_voice: str | None = None
    paragraph_count = 0
    in_paragraph = False

    for line_number, line in enumerate(text.splitlines(), 1):
        personality = PERSONALITY_HEADING.fullmatch(line)
        if personality:
            active_voice = personality.group("name")
            paragraph_count = 0
            in_paragraph = False
            continue
        if SPECIAL_HEADING.fullmatch(line):
            active_voice = "special voice"
            paragraph_count = 0
            in_paragraph = False
            continue
        if (
            THOUGHT_TITLE.fullmatch(line)
            or THOUGHT_ACQUISITION_TITLE.fullmatch(line)
            or THOUGHT_FIELD.fullmatch(line)
            or THOUGHT_ACQUISITION_OPTIONS.fullmatch(line)
        ):
            active_voice = None
            paragraph_count = 0
            in_paragraph = False
            continue

        if active_voice is None:
            continue
        if not line.startswith(">"):
            if line.strip():
                active_voice = None
            else:
                in_paragraph = False
            continue

        content = line[1:].lstrip()
        if not content:
            in_paragraph = False
            continue
        if LIST_ITEM.match(line):
            errors.append(
                f"line {line_number}: bullet list is not allowed in a Disco voice block; "
                "repeat the same voice heading for each separate point"
            )
        if not in_paragraph:
            paragraph_count += 1
            in_paragraph = True
            if paragraph_count > 1:
                errors.append(
                    f"line {line_number}: {active_voice} has multiple paragraphs under one heading; "
                    "repeat the full voice heading before the next paragraph"
                )
    return errors


def _validate_thought_cards(text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()

    for line_number, line in enumerate(lines, 1):
        if "思维已内在化" in line:
            errors.append(
                f"line {line_number}: thought card must use a standalone source-marked title and full fields; "
                "do not compress completion into an inline status strip"
            )
        if "获得思维：" in line and not THOUGHT_ACQUISITION_TITLE.fullmatch(line):
            errors.append(
                f"line {line_number}: thought acquisition title must be a standalone quoted line; "
                "do not embed it in a personality paragraph or append options"
            )
        if ("[内在化]" in line or "[放入思维阁]" in line) and not THOUGHT_ACQUISITION_OPTIONS.fullmatch(line):
            errors.append(
                f"line {line_number}: thought acquisition options must share their own quoted line "
                "below the standalone acquisition title"
            )

    for index, line in enumerate(lines):
        if THOUGHT_ACQUISITION_TITLE.fullmatch(line):
            cursor = index + 1
            while cursor < len(lines) and not lines[cursor].strip().lstrip(">").strip():
                cursor += 1
            if cursor >= len(lines) or not THOUGHT_ACQUISITION_OPTIONS.fullmatch(lines[cursor]):
                errors.append(
                    f"line {index + 1}: thought acquisition title must be followed by the standalone "
                    "[internalize] and [place in thought cabinet] option line"
                )
        if THOUGHT_ACQUISITION_OPTIONS.fullmatch(line):
            cursor = index - 1
            while cursor >= 0 and not lines[cursor].strip().lstrip(">").strip():
                cursor -= 1
            if cursor < 0 or not THOUGHT_ACQUISITION_TITLE.fullmatch(lines[cursor]):
                errors.append(
                    f"line {index + 1}: thought acquisition options are missing their standalone title"
                )

    index = 0
    while index < len(lines):
        title = THOUGHT_TITLE.fullmatch(lines[index])
        if title is None:
            index += 1
            continue

        title_line = index + 1
        fields: list[tuple[str, str, int]] = []
        cursor = index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if THOUGHT_TITLE.fullmatch(line) or PERSONALITY_HEADING.fullmatch(line) or SPECIAL_HEADING.fullmatch(line):
                break
            if line and not line.startswith(">"):
                break
            field = THOUGHT_FIELD.fullmatch(line)
            if field:
                fields.append((field.group("label"), field.group("content"), cursor + 1))
            cursor += 1

        labels = [label for label, _, _ in fields]
        expected = INTERNALIZED_THOUGHT_FIELDS if "解答" in labels else RESEARCH_THOUGHT_FIELDS
        if tuple(labels) != expected:
            errors.append(
                f"line {title_line}: thought card fields must appear once and in order: "
                + " -> ".join(expected)
            )

        if title.group("source") == "Earth":
            prose = {label: content for label, content, _ in fields}
            for label in ("问题", "解答"):
                if label in prose and len(prose[label]) < MIN_EARTH_THOUGHT_PROSE:
                    errors.append(
                        f"line {title_line}: Earth thought card {label} is too short "
                        f"({len(prose[label])} < {MIN_EARTH_THOUGHT_PROSE}); display the full continuous prose"
                    )

        index = max(cursor, index + 1)

    return errors


def _runtime_checks(runtime: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not runtime:
        return []
    checks = runtime.get("checks", [])
    if not isinstance(checks, list):
        return []
    return [item for item in checks if isinstance(item, dict) and isinstance(item.get("skill"), str)]


def validate_text(text: str, runtime: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = _validate_voice_block_rhythm(text)
    errors.extend(_validate_thought_cards(text))
    blocks = _extract_personality_blocks(text)
    errors.extend(_validate_ensemble_fidelity(blocks))
    headings: list[dict[str, str]] = []
    official_card = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        thought_title = THOUGHT_TITLE.fullmatch(line)
        if thought_title:
            official_card = thought_title.group("source") == "Elysium"
        elif (PERSONALITY_HEADING.fullmatch(line) or SPECIAL_HEADING.fullmatch(line)
              or THOUGHT_ACQUISITION_TITLE.fullmatch(line) or not line.startswith(">")):
            official_card = False
        field = THOUGHT_FIELD.fullmatch(line)
        official_prose = official_card and field is not None and field.group("label") in {"问题", "解答"}
        # Source fidelity takes priority for official thought prose; verify its source separately.
        if FORBIDDEN_CONTRAST.search(line) and not official_prose:
            errors.append(f"line {line_number}: forbidden contrast pattern ‘不是……而是……’")
        if SPECIAL_HEADING.fullmatch(line):
            continue
        match = PERSONALITY_HEADING.fullmatch(line)
        if match:
            item = match.groupdict()
            headings.append(item)
            if item["sense"] and item["name"] != "五感发达":
                errors.append(f"line {line_number}: sensory suffix is only valid for 五感发达")
            expected = COLOR_BY_ATTRIBUTE[PERSONALITY_ATTRIBUTE[item["name"]]]
            if item["color"] != expected:
                errors.append(
                    f"line {line_number}: {item['name']} color {item['color']} != {expected}"
                )
            continue
        if BAD_BOLD_HEADING.match(line):
            errors.append(f"line {line_number}: personality heading is missing the leading color block or check")
        elif PERSONALITY_LIKE_HEADING.match(line):
            errors.append(f"line {line_number}: personality heading does not use the canonical color/check template")

    if runtime is not None:
        candidate_attributes = runtime.get("candidate_attributes", [])
        if not isinstance(candidate_attributes, list):
            candidate_attributes = []
        candidate_attribute_set = {
            item for item in candidate_attributes if item in COLOR_BY_ATTRIBUTE
        }
        displayed_attribute_set = {
            PERSONALITY_ATTRIBUTE[item["name"]] for item in headings
        }
        review = runtime.get("routing_review", {})
        excluded = review.get("excluded_attributes", {}) if isinstance(review, dict) else {}
        if not isinstance(excluded, dict):
            excluded = {}
        omitted_attributes = candidate_attribute_set - displayed_attribute_set
        reviewed_omissions = bool(omitted_attributes) and all(
            isinstance(excluded.get(attribute), str) and excluded[attribute].strip()
            for attribute in omitted_attributes
        )
        if (
            len({item["name"] for item in headings}) >= 3
            and len(candidate_attribute_set) >= 2
            and len(displayed_attribute_set) == 1
            and not reviewed_omissions
        ):
            errors.append(
                "single-color collapse: runtime exposed contributing candidates from multiple attributes "
                "but the displayed ensemble uses only one attribute"
            )
        checks = _runtime_checks(runtime)
        for item in headings:
            matches = [
                check for check in checks
                if check.get("skill") == item["name"]
                and check.get("difficulty") == item["difficulty"]
                and isinstance(check.get("success"), bool)
                and ("成功" if check.get("success") else "失败") == item["result"]
            ]
            if not matches:
                errors.append(
                    f"{item['name']}: heading result does not match the current runtime check batch"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Disco output headings and current check provenance")
    parser.add_argument("--draft", type=Path, default=None, help="draft Markdown file; omit to read stdin")
    parser.add_argument("--runtime-json", type=Path, default=None, help="current check records: runtime context, merged active results, or documented passive fallback")
    args = parser.parse_args(argv)

    text = args.draft.read_text(encoding="utf-8") if args.draft else sys.stdin.read()
    runtime = json.loads(args.runtime_json.read_text(encoding="utf-8")) if args.runtime_json else None
    if runtime is not None and not isinstance(runtime, dict):
        print("Disco output validation failed: runtime JSON must be an object.")
        return 1
    errors = validate_text(text, runtime)
    if runtime is None and any(PERSONALITY_HEADING.fullmatch(line) for line in text.splitlines()):
        errors.append("ordinary personality output requires --runtime-json with current check records")
    if errors:
        print("Disco output validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Disco output validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
