from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..sources.github import github_api_headers, parse_github_full_name_from_url
from ..utils.http import try_parse_json_object
from ..utils.time import utc_now_iso_z
from ..utils.urls import GITHUB_RAW_BASE
from .ingest import DEFAULT_BIG_FILE_BYTES, DEFAULT_EXCLUDE_DIRS, DEFAULT_EXCLUDE_FILES, classify_tags, detect_language
from .symbol_index import analyze_python_source, analyze_regex_source


_FULL_NAME_RE = re.compile(r"^[^/]+/[^/]+$")


class GitHubRateLimitError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        wait_seconds: int,
        status: int,
        url: str,
        headers: dict[str, str] | None = None,
        body_preview: str = "",
    ) -> None:
        super().__init__(message)
        self.wait_seconds = int(wait_seconds or 0)
        self.status = int(status or 0)
        self.url = str(url or "")
        self.headers = dict(headers or {})
        self.body_preview = str(body_preview or "")


def _github_rate_limit_wait_seconds(*, status: int, headers: dict[str, str], body_text: str) -> int:
    """
    Best-effort extraction of a wait duration when GitHub returns rate limiting / abuse responses.
    """
    st = int(status or 0)
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    body = str(body_text or "")
    body_l = body.lower()

    raw_ra = str(h.get("retry-after") or "").strip()
    try:
        if raw_ra:
            return max(1, int(raw_ra))
    except Exception:
        pass

    raw_remaining = str(h.get("x-ratelimit-remaining") or "").strip()
    raw_reset = str(h.get("x-ratelimit-reset") or "").strip()

    try:
        remaining = int(raw_remaining) if raw_remaining else -1
    except Exception:
        remaining = -1
    try:
        reset_ts = float(raw_reset) if raw_reset else 0.0
    except Exception:
        reset_ts = 0.0

    if st == 403 and (remaining == 0 or "rate limit" in body_l):
        if reset_ts > 0.0:
            now = time.time()
            return max(1, int(reset_ts - now + 2.0))
        # Unknown reset: conservative backoff.
        return 60

    if st in {403, 429} and ("secondary rate limit" in body_l or "abuse detection" in body_l):
        return 60

    # Not confidently a rate limit response.
    return 0


_BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".tgz",
    ".tar",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".war",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".sqlite",
    ".db",
    ".bin",
}


def _is_probably_binary_path(path: str) -> bool:
    p = str(path or "").lower()
    for ext in _BINARY_EXTS:
        if p.endswith(ext):
            return True
    return False


def is_probably_binary_path(path: str) -> bool:
    return _is_probably_binary_path(path)


def _should_include_path(
    rel_path: str,
    *,
    include_globs: list[str],
    exclude_globs: list[str],
    exclude_dirs: set[str],
    exclude_files: set[str],
) -> bool:
    p = str(rel_path or "").replace("\\", "/").lstrip("/")
    if not p:
        return False
    if Path(p).name in exclude_files:
        return False
    if any(part in exclude_dirs for part in p.split("/")):
        return False
    if exclude_globs and any(fnmatch.fnmatch(p, pat) for pat in exclude_globs):
        return False
    if include_globs and not any(fnmatch.fnmatch(p, pat) for pat in include_globs):
        return False
    return True


def _github_api_get_json(url: str, *, timeout_ms: int = 30_000, retries: int = 2) -> Any:
    headers = github_api_headers()
    headers.setdefault("User-Agent", "langskills/0.1 (+local)")
    headers.setdefault("Accept", "application/vnd.github+json")

    last_err: Exception | None = None
    for attempt in range(0, max(0, int(retries or 0)) + 1):
        try:
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=max(0.001, (timeout_ms or 30_000) / 1000)) as resp:
                status = int(getattr(resp, "status", 200))
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                if not (200 <= status <= 299):
                    raise RuntimeError(f"GitHub API HTTP {status}: {url} ({text[:200]})")
                parsed = try_parse_json_object(text)
                if parsed is None:
                    raise RuntimeError(f"GitHub API: invalid JSON: {url}")
                return parsed
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            hdrs = {str(k): str(v) for k, v in getattr(getattr(e, "headers", None), "items", lambda: [])()}
            wait_s = _github_rate_limit_wait_seconds(status=status, headers=hdrs, body_text=body)
            if wait_s > 0:
                raise GitHubRateLimitError(
                    f"GitHub API rate limited (HTTP {status}); retry in ~{wait_s}s",
                    wait_seconds=wait_s,
                    status=status,
                    url=url,
                    headers=hdrs,
                    body_preview=body[:300],
                )
            last_err = RuntimeError(f"GitHub API HTTP {status}: {url} ({body[:300]})")
            retryable = status in {429, 500, 502, 503, 504}
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            retryable = True
        except Exception as e:  # pragma: no cover
            last_err = e
            retryable = False
        if not retryable or attempt >= retries:
            break
        time.sleep(0.5 * (2**attempt))

    raise RuntimeError(f"GitHub API fetch failed: {url}") from last_err


def _github_raw_fetch_bytes(url: str, *, timeout_ms: int = 30_000, retries: int = 2) -> bytes:
    headers: dict[str, str] = {"User-Agent": "langskills/0.1 (+local)", "Accept": "application/octet-stream,*/*"}
    token = str(os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_err: Exception | None = None
    for attempt in range(0, max(0, int(retries or 0)) + 1):
        try:
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=max(0.001, (timeout_ms or 30_000) / 1000)) as resp:
                status = int(getattr(resp, "status", 200))
                raw = resp.read()
                if not (200 <= status <= 299):
                    raise RuntimeError(f"GitHub raw HTTP {status}: {url}")
                return raw
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            last_err = RuntimeError(f"GitHub raw HTTP {status}: {url}")
            retryable = status in {429, 500, 502, 503, 504}
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            retryable = True
        except Exception as e:  # pragma: no cover
            last_err = e
            retryable = False
        if not retryable or attempt >= retries:
            break
        time.sleep(0.5 * (2**attempt))

    raise RuntimeError(f"GitHub raw fetch failed: {url}") from last_err


def parse_github_full_name(repo: str) -> str:
    s = str(repo or "").strip()
    if not s:
        return ""
    if "github.com" in s.lower():
        return parse_github_full_name_from_url(s)
    if _FULL_NAME_RE.match(s):
        return re.sub(r"\.git$", "", s, flags=re.IGNORECASE)
    return ""


@dataclass(frozen=True)
class RemoteBlob:
    path: str
    blob_sha: str
    size_bytes: int


def fetch_repo_tree(*, full_name: str, ref: str = "") -> tuple[str, str, list[RemoteBlob]]:
    """
    Returns (repo_url, commit_sha, blobs).
    """
    name = str(full_name or "").strip()
    if not name:
        raise ValueError("full_name is required")
    repo_url = f"https://github.com/{name}"

    # Determine ref (default branch when missing).
    ref0 = str(ref or "").strip()
    if not ref0:
        info = _github_api_get_json(f"https://api.github.com/repos/{name}")
        if not isinstance(info, dict):
            raise RuntimeError("GitHub API: invalid repo info")
        ref0 = str(info.get("default_branch") or "main")

    commit = _github_api_get_json(f"https://api.github.com/repos/{name}/commits/{quote(ref0)}")
    if not isinstance(commit, dict):
        raise RuntimeError("GitHub API: invalid commit response")
    commit_sha = str(commit.get("sha") or "").strip()
    tree_sha = ""
    cmt = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    tree = cmt.get("tree") if isinstance(cmt.get("tree"), dict) else {}
    tree_sha = str(tree.get("sha") or "").strip()
    if not commit_sha or not tree_sha:
        raise RuntimeError("GitHub API: missing commit/tree sha")

    tree_obj = _github_api_get_json(f"https://api.github.com/repos/{name}/git/trees/{tree_sha}?recursive=1")
    if not isinstance(tree_obj, dict) or not isinstance(tree_obj.get("tree"), list):
        raise RuntimeError("GitHub API: invalid tree response")

    blobs: list[RemoteBlob] = []
    for it in tree_obj.get("tree") or []:
        if not isinstance(it, dict):
            continue
        if str(it.get("type") or "") != "blob":
            continue
        p = str(it.get("path") or "").replace("\\", "/").lstrip("/")
        sha = str(it.get("sha") or "").strip()
        size = int(it.get("size") or 0)
        if not p or not sha:
            continue
        blobs.append(RemoteBlob(path=p, blob_sha=sha, size_bytes=size))

    return repo_url, commit_sha, blobs


def _decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8-sig")
        except Exception:
            return raw.decode("utf-8", errors="replace")


def index_github_repo(
    *,
    repo: str,
    ref: str,
    out_dir: Path,
    include_globs: list[str],
    exclude_globs: list[str],
    big_file_bytes: int,
    max_files: int = 0,
) -> dict[str, Any]:
    """
    Build repo_tree.json + symbol_index.jsonl for a remote GitHub repo snapshot.
    """
    full_name = parse_github_full_name(repo)
    if not full_name:
        raise ValueError(f"Invalid GitHub repo: {repo}")

    repo_url, commit_sha, blobs = fetch_repo_tree(full_name=full_name, ref=ref)

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    exclude_files = set(DEFAULT_EXCLUDE_FILES)

    big_file_bytes = int(big_file_bytes or DEFAULT_BIG_FILE_BYTES)
    max_files = int(max_files or 0)

    file_entries: list[dict[str, Any]] = []
    download_queue: list[RemoteBlob] = []

    for b in blobs:
        if not _should_include_path(
            b.path,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            exclude_dirs=exclude_dirs,
            exclude_files=exclude_files,
        ):
            continue

        binary = _is_probably_binary_path(b.path)
        big = int(b.size_bytes or 0) > big_file_bytes
        ignored = bool(binary)
        ignore_reason = "binary_ext" if binary else ""
        analysis = "structure_only" if binary or big else "full"
        analysis_reason = "binary_ext" if binary else ("big_file" if big else "")

        file_entries.append(
            {
                "path": b.path,
                "language": detect_language(b.path),
                "size_bytes": int(b.size_bytes or 0),
                "blob_sha": b.blob_sha,
                "ignored": ignored,
                "ignore_reason": ignore_reason,
                "analysis": analysis,
                "analysis_reason": analysis_reason,
                "tags": classify_tags(b.path),
            }
        )

        if analysis == "full" and not ignored:
            download_queue.append(b)

    # Download and analyze a subset of files (optional max-files guard).
    snapshot_dir = out_dir / "repo_snapshot"
    analyzed_text: dict[str, str] = {}
    download_errors: dict[str, str] = {}

    for i, b in enumerate(download_queue):
        if max_files > 0 and i >= max_files:
            break
        owner, repo_name = full_name.split("/", 1)
        raw_url = f"{GITHUB_RAW_BASE}{owner}/{repo_name}/{commit_sha}/{quote(b.path)}"
        try:
            raw = _github_raw_fetch_bytes(raw_url, timeout_ms=30_000, retries=2)
            text = _decode_text(raw)
            analyzed_text[b.path] = text
            dst = snapshot_dir / b.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
        except Exception as e:
            download_errors[b.path] = str(e)

    # Symbol index (JSONL)
    symbol_records: list[dict[str, Any]] = []
    now = utc_now_iso_z()
    for fe in file_entries:
        path = str(fe.get("path") or "")
        lang = str(fe.get("language") or "")
        analysis = str(fe.get("analysis") or "")
        blob_sha = str(fe.get("blob_sha") or "")

        meta = {
            "source_type": "github_repo",
            "repo_url": repo_url,
            "git_commit": commit_sha,
            "ref": str(ref or "").strip(),
            "blob_sha": blob_sha,
            "source_fetched_at": now,
        }

        if analysis != "full" or path in download_errors or path not in analyzed_text:
            line_count = 1
            if path in analyzed_text:
                line_count = int(analyzed_text[path].count("\n") + 1)
            symbol_records.append(
                {
                    "path": path,
                    "language": lang,
                    "start_line": 1,
                    "end_line": max(1, line_count),
                    "kind": "module",
                    "qualified_name": re.sub(r"[^a-zA-Z0-9_.]+", "_", path.replace("/", ".")).strip("."),
                    "signature": "",
                    "summary_5_10_lines": [
                        f"Module {path} ({lang}; remote; structure-only).",
                        f"Reason: {str(fe.get('analysis_reason') or 'not_fetched')}.",
                    ],
                    "imports": [],
                    "calls": [],
                    "reads_env": [],
                    "writes": [],
                    "network": False,
                    "network_hints": [],
                    "tags": ["module", "remote", *([] if not fe.get("analysis_reason") else [str(fe.get("analysis_reason"))])],
                    "analysis": "structure_only",
                    **meta,
                }
            )
            continue

        text = analyzed_text.get(path, "")
        recs: list[dict[str, Any]] = []
        if lang == "python":
            recs = analyze_python_source(rel_path=path, text=text)
        elif lang in {"javascript", "typescript", "go", "rust", "java"}:
            recs = analyze_regex_source(rel_path=path, text=text, language=lang)
        else:
            # Keep a minimal module record for other languages.
            recs = [
                {
                    "path": path,
                    "language": lang,
                    "start_line": 1,
                    "end_line": int(text.count("\n") + 1),
                    "kind": "module",
                    "qualified_name": re.sub(r"[^a-zA-Z0-9_.]+", "_", path.replace("/", ".")).strip("."),
                    "signature": "",
                    "summary_5_10_lines": [f"Module {path} ({lang}; remote; structure-only)."],
                    "imports": [],
                    "calls": [],
                    "reads_env": [],
                    "writes": [],
                    "network": False,
                    "network_hints": [],
                    "tags": ["module", "remote"],
                    "analysis": "structure_only",
                }
            ]

        for r in recs:
            r.update(meta)
            symbol_records.append(r)

    return {
        "schema_version": 1,
        "generated_at": now,
        "repo_url": repo_url,
        "full_name": full_name,
        "ref": str(ref or "").strip(),
        "git_commit": commit_sha,
        "out_dir": out_dir.as_posix(),
        "snapshot_dir": snapshot_dir.as_posix(),
        "files_total": len(file_entries),
        "files_downloaded": len(analyzed_text),
        "files_download_errors": len(download_errors),
        "symbols_total": len(symbol_records),
        "repo_tree": {"files": file_entries},
        "symbol_records": symbol_records,
    }
