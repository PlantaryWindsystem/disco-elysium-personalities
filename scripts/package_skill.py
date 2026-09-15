from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"backups", "tests", "__pycache__", ".pytest_cache", ".mypy_cache", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
PACKAGE_ARTIFACT_SUFFIXES = (".skill", ".skill.new", ".skill.rebuilt")


def should_include(path: Path, root: Path, output: Path) -> bool:
    relative = path.relative_to(root)
    # Package supported skill resources, not private notes left beside them.
    if relative.parts[0] not in {"references", "scripts", "assets", "agents"} and relative.as_posix() not in {"SKILL.md", "LICENSE", "NOTICE.md", "requirements.txt"}:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    if path == output:
        return False
    if set(relative.parts) & EXCLUDED_DIRS:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if any(path.name.endswith(suffix) for suffix in PACKAGE_ARTIFACT_SUFFIXES):
        return False
    return True


def build_package(output: Path) -> Path:
    root = SKILL_ROOT.resolve()
    output = output.resolve()
    required = (root / "SKILL.md", root / "references", root / "scripts")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing package input: {', '.join(missing)}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and should_include(path, root, output):
                archive.write(path, path.relative_to(root).as_posix())
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean Disco skill package")
    parser.add_argument(
        "--output",
        type=Path,
        default=SKILL_ROOT / "disco-elysium-personalities.skill.rebuilt",
    )
    args = parser.parse_args(argv)
    try:
        print(f"Wrote {build_package(args.output)}")
        return 0
    except (FileExistsError, FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
