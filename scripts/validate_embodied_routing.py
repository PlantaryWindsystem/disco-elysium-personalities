from __future__ import annotations

import re
import sys
from pathlib import Path


SKILL_PATH = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(__file__).resolve().parents[1] / "SKILL.md"
)
REFERENCE_DIR = SKILL_PATH.parent / "references"

CANONICAL_PERSONALITIES = (
    "逻辑思维", "博学多闻", "能说会道", "故弄玄虚", "标新立异", "见微知著",
    "平心定气", "内陆帝国", "通情达理", "争强好胜", "同舟共济", "循循善诱",
    "钢筋铁骨", "坚忍不拔", "强身健体", "食髓知味", "天人感应", "疑神疑鬼",
    "眼明手巧", "五感发达", "反应速度", "鬼祟玲珑", "能工巧匠", "从容自若",
)


ROUTE_REQUIREMENTS = {
    "钢筋铁骨": ("代谢", "循环", "疲劳", "饥饿", "器官负荷"),
    "坚忍不拔": ("疼痛", "羞辱", "创伤", "行动能力"),
    "强身健体": ("肌肉", "杠杆", "速度", "直接行动"),
    "食髓知味": ("快感", "性", "酒精", "药物", "刺激"),
    "天人感应": ("气温", "风", "建筑", "道路", "水体", "空间网络"),
    "疑神疑鬼": ("威胁", "羞辱", "失控", "战斗", "逃跑"),
    "眼明手巧": ("视线", "时机", "轨迹", "瞄准"),
    "五感发达": ("感官", "看见", "听见", "闻到", "尝到"),
    "反应速度": ("名字", "矛盾", "双关", "条件"),
    "鬼祟玲珑": ("灵活", "体面", "退路", "金钱", "效率", "门路"),
    "能工巧匠": ("手指", "触感", "结构", "工具", "锁具", "电路"),
    "从容自若": ("姿态", "呼吸", "表情", "衣着", "情绪泄漏"),
}

PROCESS_REQUIREMENTS = {
    "dual-pass routing": r"双层路由",
    "evidence-channel review": r"证据通道复核",
    "ground before interpretation": r"先报告[^\n]*再解释",
    "no colour quota": r"不得[^\n]*固定配额",
    "canonical personality vocabulary": r"人格名封闭词表",
    "fixed Half Light translation": r"Half Light[^\n]*固定写作 `疑神疑鬼`",
    "colour repeated on every appearance": r"色块逐块强制[\s\S]*每个(?:被展示的)?人格每次登场时[^\n]*重新写出所属属性色块",
    "silent thought internalization": r"选择“内在化”后[^\n]*静默[^\n]*直接显示研究卡",
    "preserve existing thoughts": r"新思维必须追加[^\n]*绝不得[^\n]*覆盖整个列表",
    "no process narration": r"禁止过程旁白[\s\S]*不得写“我要把 A 与 B 分开看”",
    "silent routine thought progress": r"未完成思维的日常推进[^\n]*不在正文末尾自动附加进度表",
    "first-use attribute allocation": r"首次启用时，第一件事是讨论四属性分配",
    "passive checks": r"日常人格使用被动检定",
    "active 2d6 checks": r"真实 `2D6` 主动检定",
    "double-one and double-six": r"双 1[\s\S]*双 6",
    "canonical heading template": r"标题先构造、后填充[\s\S]*唯一模板",
    "check provenance gate": r"检定不可伪造或半显示[\s\S]*runtime_context\.py",
    "original voice excerpts": r"原文声音摘录\.md",
    "output validator gate": r"scripts/validate_output\.py",
    "forbidden contrast style": r"全局禁用“不是……而是……”",
}

REQUIRED_FILES = (
    "references/人物卡.md",
    "references/检定系统.md",
    "scripts/character_sheet.py",
    "scripts/check_engine.py",
    "scripts/validate_output.py",
)


def route_row(text: str, name: str) -> str:
    match = re.search(rf"^\| {re.escape(name)} \|.*$", text, flags=re.MULTILINE)
    return match.group(0) if match else ""


def main() -> int:
    text = SKILL_PATH.read_text(encoding="utf-8")
    failures: list[str] = []

    for relative in REQUIRED_FILES:
        if not (SKILL_PATH.parent / relative).is_file():
            failures.append(f"missing hybrid-check file: {relative}")

    for name, cues in ROUTE_REQUIREMENTS.items():
        row = route_row(text, name)
        if not row:
            failures.append(f"missing route row: {name}")
            continue
        missing = [cue for cue in cues if cue not in row]
        if missing:
            failures.append(f"{name} missing cues: {', '.join(missing)}")

    for label, pattern in PROCESS_REQUIREMENTS.items():
        if not re.search(pattern, text):
            failures.append(f"missing process rule: {label}")

    for name in CANONICAL_PERSONALITIES:
        row = route_row(text, name)
        expected_link = f"[{name}.md](references/{name}.md)"
        if expected_link not in row:
            failures.append(f"{name} route does not use canonical reference link")

        reference_path = REFERENCE_DIR / f"{name}.md"
        if not reference_path.is_file():
            failures.append(f"missing canonical reference file: {reference_path.name}")
            continue

        first_line = reference_path.read_text(encoding="utf-8").splitlines()[0]
        if first_line != f"# {name}":
            failures.append(
                f"{reference_path.name} has non-canonical heading: {first_line!r}"
            )

    if failures:
        print("Embodied routing validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Embodied routing validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
