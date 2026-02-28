#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from pathlib import Path

def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parent


def _resolve_venv_python(repo_root: Path) -> Path | None:
    # macOS/Linux
    cand = repo_root / ".venv" / "bin" / "python"
    if cand.exists():
        return cand
    cand = repo_root / ".venv" / "bin" / "python3"
    if cand.exists():
        return cand
    # Windows
    cand = repo_root / ".venv" / "Scripts" / "python.exe"
    if cand.exists():
        return cand
    return None


def _maybe_reexec_into_venv() -> None:
    # Prefer running inside the repo's venv when it exists to avoid dependency mismatches
    # (e.g., httpx/playwright not installed in the system interpreter).
    if str(os.environ.get("LANGSKILLS_NO_VENV_REEXEC") or "").strip() == "1":
        return
    # Detect venv even when not "activated" (VIRTUAL_ENV can be empty).
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if str(base_prefix) != str(sys.prefix):
        return

    repo_root = _resolve_repo_root()
    venv_python = _resolve_venv_python(repo_root)
    if venv_python is None:
        return

    # If the current interpreter is missing key deps but the venv has them, re-exec.
    # As a conservative default, re-exec into the venv whenever it exists.

    os.execv(venv_python.as_posix(), [venv_python.as_posix(), *sys.argv])


_maybe_reexec_into_venv()

repo_root = _resolve_repo_root()
src_root = repo_root / "src"
if src_root.exists():
    sys.path.insert(0, src_root.as_posix())

from core.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
