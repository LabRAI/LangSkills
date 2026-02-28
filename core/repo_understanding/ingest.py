from __future__ import annotations

import hashlib
import fnmatch
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "captures",
    "dist",
    "runs",
    "backup",
}

DEFAULT_EXCLUDE_FILES = {
    ".env",
}

# >2MB: keep file in tree, but do not attempt deep parsing by default.
DEFAULT_BIG_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class RepoFile:
    rel_path: str
    abs_path: Path
    size_bytes: int


def detect_language(rel_path: str) -> str:
    p = str(rel_path or "").lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith(".md"):
        return "markdown"
    if p.endswith((".yml", ".yaml")):
        return "yaml"
    if p.endswith(".jsonl"):
        return "jsonl"
    if p.endswith(".json"):
        return "json"
    if p.endswith(".toml"):
        return "toml"
    if p.endswith(".ini") or p.endswith(".cfg"):
        return "ini"
    if p.endswith((".sh", ".bash", ".zsh")):
        return "shell"
    if p.endswith(".ts"):
        return "typescript"
    if p.endswith(".js"):
        return "javascript"
    if p.endswith(".go"):
        return "go"
    if p.endswith(".rs"):
        return "rust"
    if p.endswith(".java"):
        return "java"
    if p.endswith((".cc", ".cpp", ".cxx", ".c")):
        return "cpp"
    if p.endswith((".h", ".hpp", ".hh")):
        return "c_header"
    if p.endswith(".rb"):
        return "ruby"
    if p.endswith(".php"):
        return "php"
    if p.endswith(".kt"):
        return "kotlin"
    if p.endswith(".swift"):
        return "swift"
    if p.endswith(".sql"):
        return "sql"
    if p.endswith(".txt"):
        return "text"
    if p.endswith((".dockerfile", "dockerfile")):
        return "dockerfile"
    if p.endswith((".makefile", "makefile")):
        return "makefile"
    mt, _ = mimetypes.guess_type(p)
    if mt == "text/plain":
        return "text"
    return "unknown"


def classify_tags(rel_path: str) -> list[str]:
    p = str(rel_path or "").replace("\\", "/").lstrip("/")
    tags: list[str] = []

    if p.startswith("langskills/") or p.startswith(("src/", "lib/", "app/", "pkg/", "cmd/")):
        tags.append("src")
    if p.startswith("scripts/") or p == "langskills_cli.py":
        tags.append("script")
    if p.startswith("docs/") or p.lower().startswith("readme"):
        tags.append("doc")
    if p.startswith("config/"):
        tags.append("config")
    if p.startswith("tests/") or p.startswith("test/"):
        tags.append("test")
    if p.startswith(".github/workflows/"):
        tags.append("ci")

    if not tags:
        tags.append("other")
    return tags


def is_binary_file(path: str | Path, *, sample_bytes: int = 2048) -> bool:
    p = Path(path)
    try:
        chunk = p.open("rb").read(max(1, int(sample_bytes or 2048)))
    except Exception:
        return True
    if b"\x00" in chunk:
        return True
    # Heuristic: if it can't decode as UTF-8 and looks like high-entropy bytes, treat as binary.
    try:
        chunk.decode("utf-8")
    except Exception:
        return True
    return False


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def mtime_iso(path: str | Path) -> str:
    try:
        ts = float(Path(path).stat().st_mtime)
    except Exception:
        return ""
    # Keep it human-friendly but deterministic for audit; local timezones are avoided.
    import datetime as _dt

    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_excluded_path(rel_path: str, *, exclude_globs: list[str]) -> bool:
    for pat in exclude_globs:
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def iter_repo_files(
    repo_root: str | Path,
    *,
    include_globs: list[str],
    exclude_globs: list[str] | None = None,
    exclude_dirs: set[str] | None = None,
    exclude_files: set[str] | None = None,
) -> list[RepoFile]:
    root = Path(repo_root).resolve()
    exclude_globs = list(exclude_globs or [])
    exclude_dirs = set(exclude_dirs or DEFAULT_EXCLUDE_DIRS)
    exclude_files = set(exclude_files or DEFAULT_EXCLUDE_FILES)

    out: list[RepoFile] = []
    seen: set[str] = set()

    for pat in include_globs:
        for p in root.glob(pat):
            if p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_dir():
                        if sub.name in exclude_dirs:
                            # Prune: rglob can't be pruned directly; rely on filter below.
                            continue
                        continue
                    if not sub.is_file():
                        continue
                    if sub.name in exclude_files:
                        continue
                    rel = sub.relative_to(root).as_posix()
                    if any(part in exclude_dirs for part in sub.relative_to(root).parts):
                        continue
                    if _is_excluded_path(rel, exclude_globs=exclude_globs):
                        continue
                    if rel in seen:
                        continue
                    seen.add(rel)
                    try:
                        size = sub.stat().st_size
                    except OSError:
                        size = 0
                    out.append(RepoFile(rel_path=rel, abs_path=sub, size_bytes=int(size)))
            elif p.is_file():
                if p.name in exclude_files:
                    continue
                rel = p.relative_to(root).as_posix()
                if any(part in exclude_dirs for part in p.relative_to(root).parts):
                    continue
                if _is_excluded_path(rel, exclude_globs=exclude_globs):
                    continue
                if rel in seen:
                    continue
                seen.add(rel)
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                out.append(RepoFile(rel_path=rel, abs_path=p, size_bytes=int(size)))

    out.sort(key=lambda r: r.rel_path)
    return out


def build_repo_tree_top_level(repo_root: str | Path) -> list[dict[str, object]]:
    root = Path(repo_root).resolve()
    entries: list[dict[str, object]] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        name = p.name
        if name in DEFAULT_EXCLUDE_DIRS or name in DEFAULT_EXCLUDE_FILES:
            continue
        if name.startswith(".") and name not in {".editorconfig", ".gitignore", ".github"}:
            continue
        kind = "dir" if p.is_dir() else "file"
        size = 0
        if p.is_file():
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
        entries.append({"name": name, "type": kind, "size_bytes": int(size)})
    return entries


def summarize_env_presence(keys: Iterable[str]) -> dict[str, bool]:
    env = os.environ
    return {k: bool(str(env.get(k, "")).strip()) for k in keys}
