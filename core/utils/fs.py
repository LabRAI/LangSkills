from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .hashing import sha256_hex
from .time import utc_stamp_compact
from .hashing import slugify


def path_exists(path: str | Path) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


def ensure_dir(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_json(path: str | Path, default: object | None = None) -> object | None:
    p = Path(path)
    if not p.exists():
        return default
    try:
        # utf-8-sig strips optional BOM from legacy files.
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_text_atomic(path: str | Path, content: str) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    tmp = p.with_name(f"{p.name}.{os.urandom(4).hex()}.tmp")
    tmp.write_text(str(content or ""), encoding="utf-8")
    os.replace(tmp, p)


def write_json_atomic(path: str | Path, obj: object) -> None:
    write_text_atomic(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def rmrf(path: str | Path) -> None:
    p = Path(path)
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    except Exception:
        return


def unique_dir(path: str | Path) -> Path:
    p = Path(path)
    if not p.exists():
        return p
    suffix = os.urandom(3).hex()
    return Path(f"{p}-{suffix}")


def make_run_dir(repo_root: str | Path, topic: str) -> Path:
    run_id = f"run-{utc_stamp_compact()}-{slugify(topic, 24)}"
    out_root = Path(repo_root) / "captures"
    return unique_dir(out_root / run_id)


def list_capture_runs(repo_root: str | Path) -> list[str]:
    captures_dir = Path(repo_root) / "captures"
    if not captures_dir.exists():
        return []
    runs = [p.name for p in captures_dir.iterdir() if p.is_dir() and p.name.startswith("run-")]
    return sorted(runs)


def resolve_run_dir(repo_root: str | Path, run_target: str) -> Path:
    raw = str(run_target or "").strip()
    captures_dir = Path(repo_root) / "captures"

    if not raw or raw.lower() == "latest":
        runs = list_capture_runs(repo_root)
        if not runs:
            raise FileNotFoundError("No runs found under captures/")
        return captures_dir / runs[-1]

    direct = Path(raw)
    if not direct.is_absolute():
        direct = Path(repo_root) / raw
    if direct.exists():
        return direct

    under_captures = captures_dir / raw
    if under_captures.exists():
        return under_captures

    raise FileNotFoundError(f"Run not found: {raw}")


def list_skill_dirs(root_dir: str | Path) -> list[Path]:
    root = Path(root_dir)
    results: list[Path] = []
    stack: list[Path] = [root]

    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue

        if any(e.is_file() and e.name == "skill.md" for e in entries):
            results.append(cur)
            continue

        for e in entries:
            if e.is_dir():
                stack.append(e)

    results.sort(key=lambda p: str(p))
    return results


def find_nearest_sources_dir(start_dir: str | Path) -> Path | None:
    cur = Path(start_dir)
    for _ in range(0, 8):
        cand = cur / "sources"
        if cand.exists() and cand.is_dir():
            return cand
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def relpath_posix(path: str | Path, start: str | Path) -> str:
    return Path(path).resolve().relative_to(Path(start).resolve()).as_posix()


def can_write_dir(dir_path: str | Path) -> bool:
    try:
        p = Path(dir_path)
        ensure_dir(p)
        tmp = p / f".tmp-{os.getpid()}-{os.urandom(4).hex()}.txt"
        tmp.write_text("ok", encoding="utf-8")
        tmp.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def source_id_for_url(url: str) -> str:
    return sha256_hex(str(url or "").strip())
