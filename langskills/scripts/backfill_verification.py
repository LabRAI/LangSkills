from __future__ import annotations

import argparse
import re
from pathlib import Path

from ..utils.fs import list_skill_dirs, read_text, write_text_atomic


def _section_bounds(lines: list[str], heading_re: re.Pattern[str]) -> tuple[int, int] | None:
    start = -1
    for i, line in enumerate(lines):
        if heading_re.match(line.strip()):
            start = i + 1
            break
    if start < 0:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[j].strip()):
            end = j
            break
    return start, end


def _ensure_verification_block(md: str, *, skill_id: str) -> tuple[str, bool]:
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    heading_re = re.compile(r"^##\s+Verification\s*$", flags=re.IGNORECASE)
    bounds = _section_bounds(lines, heading_re)

    block = [
        "```bash",
        f"# Verification stub for {skill_id}",
        "printf \"verification: ok\\n\"",
        "```",
    ]

    if bounds is None:
        out = lines[:]
        if out and out[-1].strip():
            out.append("")
        out.extend(["## Verification", ""])
        out.extend(block)
        return "\n".join(out).rstrip() + "\n", True

    start, end = bounds
    section = "\n".join(lines[start:end])
    if len(re.findall(r"```", section)) // 2 >= 1:
        return "\n".join(lines).rstrip() + "\n", False

    insert_at = end
    out = lines[:insert_at]
    if out and out[-1].strip():
        out.append("")
    out.extend(block)
    if insert_at < len(lines):
        out.append("")
        out.extend(lines[insert_at:])
    return "\n".join(out).rstrip() + "\n", True


def cli_backfill_verification(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills backfill-verification")
    parser.add_argument("--root", default="skills/by-skill")
    parser.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    root = Path(ns.root)
    if not root.is_absolute():
        root = (repo_root / root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root not found: {root}")

    touched = 0
    for d in list_skill_dirs(root):
        md_path = d / "skill.md"
        if not md_path.exists():
            continue
        md = read_text(md_path)
        updated, changed = _ensure_verification_block(md, skill_id=d.name)
        if changed:
            touched += 1
            if not ns.dry_run:
                write_text_atomic(md_path, updated)

    print(f"Backfill complete. touched={touched} dry_run={bool(ns.dry_run)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_backfill_verification())
