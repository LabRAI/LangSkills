from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_commit(repo_root: str | Path) -> str:
    """
    Best-effort: return current git commit SHA, or "" if unavailable.
    """
    root = Path(repo_root)
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    sha = str(p.stdout or "").strip()
    return sha if sha and p.returncode == 0 else ""

