from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    # langskills/utils/paths.py -> repo root
    return Path(__file__).resolve().parents[2]
