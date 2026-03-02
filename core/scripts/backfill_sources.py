from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..sources.store import write_global_source_from_artifact
from ..utils.fs import read_json, relpath_posix


def _iter_source_artifacts(repo_root: Path) -> list[Path]:
    out: list[Path] = []
    captures_root = repo_root / "captures"
    if captures_root.exists():
        out.extend(sorted(captures_root.rglob("sources/*.json")))
    by_skill_root = repo_root / "skills" / "by-skill"
    if by_skill_root.exists():
        out.extend(sorted(by_skill_root.rglob("source.json")))
    return out


def cli_backfill_sources(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai backfill-sources")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    source_files = _iter_source_artifacts(repo_root)
    written = 0
    skipped = 0

    for path in source_files:
        if "sources" in path.parts and "by-id" in path.parts:
            continue
        try:
            data = read_json(path)
        except Exception:
            skipped += 1
            continue
        if not isinstance(data, dict):
            skipped += 1
            continue
        source_id = str(data.get("source_id") or "").strip()
        if not source_id:
            skipped += 1
            continue

        dest_dir = repo_root / "sources" / "by-id" / source_id
        if dest_dir.exists() and not ns.overwrite:
            skipped += 1
            continue

        if not ns.dry_run:
            write_global_source_from_artifact(
                repo_root=repo_root,
                artifact=data,
                artifact_path=path,
                overwrite=True,
            )
        written += 1

    print(f"Backfill sources complete. files={len(source_files)} written={written} skipped={skipped} dry_run={bool(ns.dry_run)}")
    if source_files:
        print(f"First source: {relpath_posix(source_files[0], repo_root)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_backfill_sources())
