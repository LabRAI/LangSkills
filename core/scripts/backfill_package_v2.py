from __future__ import annotations

import argparse
from pathlib import Path

from ..env import load_dotenv
from ..llm.factory import create_llm_from_env
from ..skills.package_v2 import generate_package_v2_for_skill_dir
from ..utils.fs import list_skill_dirs


def _has_package_files(skill_dir: Path) -> bool:
    lib = skill_dir / "library.md"
    ref = skill_dir / "reference"
    required = [ref / fn for fn in ("sources.md", "troubleshooting.md", "edge-cases.md", "examples.md", "changelog.md")]
    return lib.exists() and ref.exists() and ref.is_dir() and all(p.exists() for p in required)


def cli_backfill_package_v2(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills backfill-package-v2")
    parser.add_argument("--root", default="skills")
    parser.add_argument("--provider", dest="provider", default=None)
    parser.add_argument("--llm", dest="provider", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true", dest="overwrite")
    parser.add_argument("--force", action="store_true", dest="overwrite", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root)

    root_dir = Path(ns.root)
    if not root_dir.is_absolute():
        root_dir = (repo_root / root_dir).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"Missing root dir: {root_dir}")
        return 2

    llm = create_llm_from_env(provider_override=ns.provider)

    dirs = list_skill_dirs(root_dir)
    print(f"Found skills: {len(dirs)} (root={root_dir.relative_to(repo_root).as_posix() if root_dir.is_relative_to(repo_root) else str(root_dir)})")

    processed = 0
    skipped = 0
    ok = 0
    failed = 0

    for d in dirs:
        if ns.limit and processed >= ns.limit:
            break
        processed += 1
        rel = d.relative_to(repo_root).as_posix() if d.is_relative_to(repo_root) else str(d)

        if not ns.overwrite and _has_package_files(d):
            skipped += 1
            print(f"SKIP: {rel} (already has package files)")
            continue

        try:
            generate_package_v2_for_skill_dir(skill_dir=d, llm=llm)
            ok += 1
            print(f"OK: {rel}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {rel}: {e}")

    print(f"\nSummary: processed={processed} ok={ok} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_backfill_package_v2())
