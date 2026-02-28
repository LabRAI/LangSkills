from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ingest import RepoFile, mtime_iso, sha256_file


STATE_SCHEMA_VERSION = 1
INDEXER_VERSION = 3


def load_repo_state(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def build_repo_state(
    *,
    repo_root: str | Path,
    files: list[RepoFile],
    prev_state: dict[str, Any] | None = None,
    git_commit: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    prev_files = prev_state.get("files") if isinstance(prev_state, dict) else None
    prev_files = prev_files if isinstance(prev_files, dict) else {}

    out_files: dict[str, dict[str, Any]] = {}

    for rf in files:
        rel = rf.rel_path
        meta_prev = prev_files.get(rel) if isinstance(prev_files, dict) else None
        size_bytes = int(rf.size_bytes)
        mtime = mtime_iso(rf.abs_path)

        sha = ""
        if isinstance(meta_prev, dict) and int(meta_prev.get("size_bytes") or 0) == size_bytes and str(meta_prev.get("mtime") or "") == mtime:
            sha = str(meta_prev.get("sha256") or "")
        if not sha:
            try:
                sha = sha256_file(rf.abs_path)
            except Exception:
                sha = ""

        out_files[rel] = {
            "size_bytes": size_bytes,
            "mtime": mtime,
            "sha256": sha,
        }

    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "indexer_version": INDEXER_VERSION,
        "repo_root": str(Path(repo_root).resolve()),
        "git_commit": str(git_commit or ""),
        "generated_at": str(generated_at or ""),
        "files": out_files,
    }


def changed_paths(prev_state: dict[str, Any] | None, new_state: dict[str, Any]) -> set[str]:
    """
    Compare two repo_state dicts and return the set of paths that changed OR were removed.
    """
    prev_files = prev_state.get("files") if isinstance(prev_state, dict) else None
    prev_files = prev_files if isinstance(prev_files, dict) else {}
    new_files = new_state.get("files") if isinstance(new_state, dict) else None
    new_files = new_files if isinstance(new_files, dict) else {}

    changed: set[str] = set()

    for rel, meta in new_files.items():
        prev = prev_files.get(rel) if isinstance(prev_files, dict) else None
        if not isinstance(prev, dict):
            changed.add(rel)
            continue
        if str(prev.get("sha256") or "") != str(meta.get("sha256") or ""):
            changed.add(rel)

    for rel in prev_files.keys():
        if rel not in new_files:
            changed.add(rel)

    return changed
