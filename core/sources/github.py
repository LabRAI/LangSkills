from __future__ import annotations

import os
import re
import datetime as _dt
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, quote_plus, unquote, urlsplit

from ..config import canonicalize_source_url
from ..utils.http import HttpError, fetch_with_retries, try_parse_json_object
from ..utils.paths import repo_root
from ..utils.text import truncate_text
from ..utils.urls import GITHUB_RAW_BASE
from .types import FetchResult


@dataclass(frozen=True)
class GithubRepo:
    full_name: str
    html_url: str
    description: str
    stargazers_count: int
    language: str
    default_branch: str
    license_spdx: str
    pushed_at: str = ""


def github_api_headers() -> dict[str, str]:
    """
    GitHub REST API headers with optional auth.

    Uses `GITHUB_TOKEN` when present to reduce rate-limit failures.
    """
    headers: dict[str, str] = {"X-GitHub-Api-Version": "2022-11-28"}
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_search_min_interval_sec() -> float:
    raw = str(os.environ.get("LANGSKILLS_GITHUB_SEARCH_MIN_INTERVAL_SEC") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except Exception:
            return 2.2
    # GitHub Search API is heavily rate limited; pick conservative defaults.
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    return 2.2 if token else 6.5


def _github_rate_lock_path() -> str:
    p = repo_root() / "runs" / "github_search_rate.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.as_posix()


def _github_get_next_allowed_ts() -> float:
    if str(os.environ.get("LANGSKILLS_GITHUB_DISABLE_GLOBAL_THROTTLE") or "").strip() == "1":
        return 0.0
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover - non-POSIX platforms
        return 0.0
    path = _github_rate_lock_path()
    try:
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                try:
                    return float(raw) if raw else 0.0
                except Exception:
                    return 0.0
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        return 0.0


def _github_should_skip_search() -> bool:
    next_ts = _github_get_next_allowed_ts()
    return time.time() < float(next_ts or 0.0)


def _github_global_throttle(min_interval_sec: float) -> None:
    if float(min_interval_sec or 0.0) <= 0.0:
        return
    if str(os.environ.get("LANGSKILLS_GITHUB_DISABLE_GLOBAL_THROTTLE") or "").strip() == "1":
        return
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover - non-POSIX platforms
        return

    path = _github_rate_lock_path()
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip()
            try:
                next_ts = float(raw) if raw else 0.0
            except Exception:
                next_ts = 0.0
            now = time.time()
            if now < next_ts:
                time.sleep(max(0.0, next_ts - now))
                now = time.time()
            f.seek(0)
            f.truncate()
            f.write(str(now + float(min_interval_sec)))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _github_global_backoff(seconds: float) -> None:
    """
    Apply a cross-process backoff by pushing the shared next-allowed timestamp forward.
    """
    sec = float(seconds or 0.0)
    if sec <= 0.0:
        return
    if str(os.environ.get("LANGSKILLS_GITHUB_DISABLE_GLOBAL_THROTTLE") or "").strip() == "1":
        return
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover - non-POSIX platforms
        time.sleep(min(60.0, sec))
        return

    path = _github_rate_lock_path()
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip()
            try:
                cur_next = float(raw) if raw else 0.0
            except Exception:
                cur_next = 0.0
            now = time.time()
            new_next = max(cur_next, now + sec)
            f.seek(0)
            f.truncate()
            f.write(str(new_next))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _github_retry_after_seconds(err: HttpError) -> float:
    headers = getattr(err, "headers", {}) or {}
    # Prefer explicit Retry-After if available.
    raw_ra = str(headers.get("Retry-After") or headers.get("retry-after") or "").strip()
    try:
        if raw_ra:
            return max(1.0, float(int(raw_ra)))
    except Exception:
        pass
    # If primary rate limit hit, GitHub returns a reset epoch.
    raw_reset = str(headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset") or "").strip()
    raw_remaining = str(headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining") or "").strip()
    try:
        reset_ts = float(raw_reset) if raw_reset else 0.0
    except Exception:
        reset_ts = 0.0
    try:
        remaining = int(raw_remaining) if raw_remaining else -1
    except Exception:
        remaining = -1
    now = time.time()
    if reset_ts > 0 and (remaining == 0 or remaining < 0):
        return max(1.0, reset_ts - now + 1.0)
    # Secondary rate limit / abuse detection: default backoff.
    body = str(getattr(err, "body_preview", "") or "").lower()
    if "secondary rate limit" in body or "abuse detection" in body:
        return 60.0
    return 15.0


def _has_stars_qualifier(query: str) -> bool:
    return bool(re.search(r"(?:^|\s)stars:\S+", str(query or ""), flags=re.IGNORECASE))


def _has_pushed_qualifier(query: str) -> bool:
    return bool(re.search(r"(?:^|\s)pushed:\S+", str(query or ""), flags=re.IGNORECASE))


def _parse_iso_datetime(raw: str) -> _dt.datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt
    except Exception:
        return None


def github_search_top_repos(
    *,
    query: str,
    per_page: int = 10,
    min_stars: int | None = None,
    pushed_after: str | None = None,
    page: int = 1,
    skip_if_throttled: bool = False,
) -> list[GithubRepo]:
    q = str(query or "").strip()
    min_stars_n = 0
    try:
        min_stars_n = int(min_stars or 0)
    except Exception:
        min_stars_n = 0
    if min_stars_n > 0 and not _has_stars_qualifier(q):
        q = f"{q} stars:>={min_stars_n}".strip()
    pushed_raw = str(pushed_after or "").strip()
    if pushed_raw and not _has_pushed_qualifier(q):
        if "pushed:" in pushed_raw.lower():
            qualifier = pushed_raw
        elif re.match(r"^[<>]=?|^=", pushed_raw):
            qualifier = f"pushed:{pushed_raw}"
        else:
            qualifier = f"pushed:>{pushed_raw}"
        q = f"{q} {qualifier}".strip()
    n = max(1, min(100, int(per_page or 10)))
    page_n = max(1, min(10, int(page or 1)))
    url = f"https://api.github.com/search/repositories?q={quote_plus(q)}&sort=stars&order=desc&per_page={n}&page={page_n}"
    if bool(skip_if_throttled) and _github_should_skip_search():
        return []
    _github_global_throttle(_github_search_min_interval_sec())
    try:
        resp = fetch_with_retries(
            url,
            timeout_ms=20_000,
            retries=2,
            accept="application/vnd.github+json",
            headers=github_api_headers(),
        )
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) in {403, 429}:
            _github_global_backoff(_github_retry_after_seconds(e))
            if bool(skip_if_throttled):
                return []
        raise
    except Exception:
        # Network failures (offline, DNS, transient) shouldn't spam logs from discovery loops.
        _github_global_backoff(60.0)
        if bool(skip_if_throttled):
            return []
        raise
    parsed = try_parse_json_object(resp.text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise RuntimeError("GitHub search: invalid JSON response")

    pushed_after_dt = _parse_iso_datetime(pushed_raw) if pushed_raw else None
    out: list[GithubRepo] = []
    for it in parsed["items"][:n]:
        if not isinstance(it, dict):
            continue
        license_block = it.get("license") if isinstance(it.get("license"), dict) else {}
        repo = GithubRepo(
            full_name=str(it.get("full_name") or ""),
            html_url=str(it.get("html_url") or ""),
            description=str(it.get("description") or ""),
            stargazers_count=int(it.get("stargazers_count") or 0),
            language=str(it.get("language") or ""),
            default_branch=str(it.get("default_branch") or "main"),
            license_spdx=str(license_block.get("spdx_id") or "") if isinstance(license_block, dict) else "",
            pushed_at=str(it.get("pushed_at") or ""),
        )
        if min_stars_n > 0 and repo.stargazers_count < min_stars_n:
            continue
        if pushed_after_dt:
            repo_dt = _parse_iso_datetime(repo.pushed_at)
            if repo_dt and repo_dt < pushed_after_dt:
                continue
        out.append(repo)
    return out


def _default_star_buckets(min_stars: int) -> list[tuple[int, int | None]]:
    edges = [
        0,
        10,
        50,
        100,
        200,
        500,
        1000,
        2000,
        5000,
        10000,
        20000,
        50000,
        100000,
        200000,
        500000,
        1000000,
        2000000,
        5000000,
        10000000,
    ]
    out: list[tuple[int, int | None]] = []
    for idx, low in enumerate(edges):
        if low < min_stars:
            continue
        high = edges[idx + 1] if idx + 1 < len(edges) else None
        out.append((low, high))
    if not out:
        out.append((min_stars, None))
    return out


def github_search_top_repos_traverse(
    *,
    query: str,
    per_page: int = 50,
    pages_per_bucket: int = 1,
    max_results: int = 200,
    min_stars: int | None = None,
    pushed_after: str | None = None,
    start_bucket: int = 0,
    start_page: int = 1,
) -> list[GithubRepo]:
    """
    Traverse GitHub search using star buckets + pagination to increase coverage.
    """
    q = str(query or "").strip()
    min_stars_n = 0
    try:
        min_stars_n = int(min_stars or 0)
    except Exception:
        min_stars_n = 0

    # If the caller already specified a stars qualifier, fall back to normal paging.
    if _has_stars_qualifier(q):
        out: list[GithubRepo] = []
        seen: set[str] = set()
        page0 = max(1, int(start_page or 1))
        for page in range(page0, page0 + max(1, int(pages_per_bucket or 1))):
            if len(out) >= max_results:
                break
            if page > 10:
                break
            items = github_search_top_repos(
                query=q,
                per_page=per_page,
                min_stars=min_stars_n,
                pushed_after=pushed_after,
                page=page,
            )
            for r in items:
                key = r.full_name or r.html_url
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(r)
                if len(out) >= max_results:
                    break
        return out

    buckets = _default_star_buckets(min_stars_n)
    if buckets:
        off = int(start_bucket or 0) % len(buckets)
        if off:
            buckets = buckets[off:] + buckets[:off]
    out: list[GithubRepo] = []
    seen: set[str] = set()
    base_page = max(1, int(start_page or 1))
    for b_idx, (low, high) in enumerate(buckets):
        if len(out) >= max_results:
            break
        if high is None:
            stars_q = f"stars:>={low}" if low > 0 else ""
        else:
            stars_q = f"stars:>={low} stars:<{high}" if low > 0 else f"stars:<{high}"
        q_bucket = f"{q} {stars_q}".strip()
        # Rotate start page per bucket to avoid always hitting page 1.
        page0 = 1 + ((base_page - 1 + b_idx) % 10)
        for page in range(page0, page0 + max(1, int(pages_per_bucket or 1))):
            if len(out) >= max_results:
                break
            if page > 10:
                break
            items = github_search_top_repos(
                query=q_bucket,
                per_page=per_page,
                min_stars=min_stars_n,
                pushed_after=pushed_after,
                page=page,
            )
            for r in items:
                key = r.full_name or r.html_url
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(r)
                if len(out) >= max_results:
                    break
    return out


def _candidate_branches(default_branch: str) -> list[str]:
    branches: list[str] = []
    b0 = str(default_branch or "").strip()
    if b0:
        branches.append(b0)
    branches.extend(["main", "master"])
    # de-dupe while preserving order
    out: list[str] = []
    seen: set[str] = set()
    for b in branches:
        if b in seen:
            continue
        seen.add(b)
        out.append(b)
    return out


def github_fetch_readme_excerpt_raw(*, full_name: str, default_branch: str) -> str:
    name = str(full_name or "").strip()
    if not name or not re.match(r"^[^/]+/[^/]+$", name):
        return ""
    owner, repo = name.split("/", 1)
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)

    filenames = [
        "README.md",
        "README.MD",
        "Readme.md",
        "readme.md",
        "README.rst",
        "README.RST",
        "Readme.rst",
        "readme.rst",
        "README.txt",
        "README.TXT",
        "Readme.txt",
        "readme.txt",
        "README",
        "Readme",
        "readme",
    ]
    for br in _candidate_branches(default_branch):
        for fn in filenames:
            url = f"{GITHUB_RAW_BASE}{owner}/{repo}/{quote(br)}/{fn}"
            try:
                resp = fetch_with_retries(url, timeout_ms=20_000, retries=1, accept="text/plain,*/*")
                return truncate_text(resp.text, 6000)
            except Exception:
                # try next candidate
                continue
    return ""


def parse_github_full_name_from_url(url: str) -> str:
    u = str(url or "").strip()
    m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+)(?:[/?#]|$)", u, flags=re.IGNORECASE)
    if not m:
        return ""
    owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2), flags=re.IGNORECASE)
    return f"{owner}/{repo}" if owner and repo else ""


def parse_github_blob_url(url: str) -> tuple[str, str, str] | None:
    """
    Parse a GitHub blob URL:
      https://github.com/<owner>/<repo>/blob/<ref>/<path>
    Returns (full_name, ref, path) or None.
    """
    u = str(url or "").strip()
    if not u:
        return None
    try:
        parts = urlsplit(u)
    except Exception:
        return None
    host = str(parts.hostname or "").strip().lower()
    if host != "github.com":
        return None
    segs = [s for s in str(parts.path or "").split("/") if s]
    if len(segs) < 5 or segs[2] != "blob":
        return None
    owner, repo = segs[0], re.sub(r"\.git$", "", segs[1], flags=re.IGNORECASE)
    ref = unquote(str(segs[3] or "").strip())
    path = unquote("/".join(segs[4:]).strip("/"))
    if not owner or not repo or not ref or not path:
        return None
    return (f"{owner}/{repo}", ref, path)


def _github_raw_fetch_limited(
    url: str,
    *,
    timeout_ms: int,
    max_bytes: int,
    retries: int = 2,
) -> tuple[bytes, bool]:
    import urllib.error
    import urllib.request

    lim = max(1, int(max_bytes or 1))
    headers: dict[str, str] = {"User-Agent": "langskills/0.1 (+local)", "Accept": "text/plain,*/*"}
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_err: Exception | None = None
    for attempt in range(0, max(0, int(retries or 0)) + 1):
        try:
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=max(0.001, (timeout_ms or 20_000) / 1000)) as resp:
                status = int(getattr(resp, "status", 200))
                raw = resp.read(lim + 1)
                if not (200 <= status <= 299):
                    raise HttpError(f"HTTP {status}: {url}", status=status, body_preview=raw[:2000].decode("utf-8", errors="replace"))
                return (raw[:lim], len(raw) > lim)
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            last_err = HttpError(f"HTTP {status}: {url}", status=status, body_preview=body_text[:2000])
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
    if isinstance(last_err, HttpError):
        raise last_err
    raise RuntimeError(f"Fetch failed: {url}") from last_err


def github_fetch_blob_raw_text(
    *,
    full_name: str,
    ref: str,
    path: str,
    timeout_ms: int = 20_000,
    max_bytes: int = 80_000,
) -> tuple[str, dict[str, Any]]:
    name = str(full_name or "").strip()
    if not name or not re.match(r"^[^/]+/[^/]+$", name):
        return ("", {"status": "invalid_full_name"})
    ref0 = str(ref or "").strip()
    rel = str(path or "").replace("\\", "/").lstrip("/")
    if not ref0 or not rel:
        return ("", {"status": "invalid_path"})
    owner, repo = name.split("/", 1)
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)
    raw_url = f"{GITHUB_RAW_BASE}{owner}/{repo}/{quote(ref0)}/{quote(rel, safe='/')}"
    b, truncated = _github_raw_fetch_limited(raw_url, timeout_ms=timeout_ms, max_bytes=max_bytes, retries=2)
    text = b.decode("utf-8", errors="replace")
    return (text, {"raw_url": raw_url, "truncated": bool(truncated), "bytes": len(b)})


def combine_repo_text(repo: GithubRepo, readme: str) -> str:
    return truncate_text(f"{repo.description}\n\n{readme}", 12_000)


def _fetch_repo_metadata(full_name: str, *, timeout_ms: int) -> dict[str, Any] | None:
    name = str(full_name or "").strip()
    if not name or not re.match(r"^[^/]+/[^/]+$", name):
        return None
    api = f"https://api.github.com/repos/{name}"
    try:
        resp = fetch_with_retries(
            api,
            timeout_ms=max(2_000, min(180_000, int(timeout_ms or 20_000))),
            retries=1,
            accept="application/vnd.github+json",
            headers=github_api_headers(),
        )
        parsed = try_parse_json_object(resp.text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def fetch_github_text(
    url: str,
    *,
    timeout_ms: int = 20_000,
    info: dict[str, Any] | None = None,
) -> FetchResult:
    """
    Fetch GitHub content for skill generation.

    Supports:
    - repo root URL: description + README excerpt
    - blob URL: pinned file content (via raw.githubusercontent.com)

    This is intended for debugging source acquisition, not for full repository indexing.
    """
    u = str(url or "").strip()
    if not u:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="github", used_playwright=False)

    blob = parse_github_blob_url(u)
    if blob:
        full_name, ref, path = blob
        try:
            max_bytes = int(str(os.environ.get("LANGSKILLS_GITHUB_RAW_MAX_BYTES") or "").strip() or 80_000)
        except Exception:
            max_bytes = 80_000
        debug: dict[str, Any] = {}
        try:
            content, meta = github_fetch_blob_raw_text(full_name=full_name, ref=ref, path=path, timeout_ms=timeout_ms, max_bytes=max_bytes)
            if info is not None:
                info["mode"] = "blob"
                info["full_name"] = full_name
                info["ref"] = ref
                info["path"] = path
                info["max_bytes"] = int(max_bytes)
                info.update({k: v for k, v in meta.items() if k != "raw_url"})
                debug["github"] = info
            final_url = canonicalize_source_url(u) or u
            title = f"{full_name}:{path}"
            return FetchResult(
                raw_html=content,
                extracted_text=content,
                final_url=final_url,
                title=title,
                platform="github",
                used_playwright=False,
                debug=debug,
            )
        except Exception:
            # Fall back to webpage HTML for debugging if raw fetch fails.
            from .webpage import fetch_webpage_text

            if info is not None:
                info["mode"] = "blob_fallback_webpage"
            return fetch_webpage_text(u, timeout_ms=timeout_ms, retries=1)

    full_name = parse_github_full_name_from_url(u)
    if not full_name:
        from .webpage import fetch_webpage_text

        if info is not None:
            info["status"] = "fallback_webpage"
        return fetch_webpage_text(u, timeout_ms=timeout_ms, retries=1)

    meta = _fetch_repo_metadata(full_name, timeout_ms=timeout_ms) or {}
    default_branch = str(meta.get("default_branch") or "main")
    description = str(meta.get("description") or "")
    html_url = str(meta.get("html_url") or f"https://github.com/{full_name}")
    language = str(meta.get("language") or "")
    try:
        stars = int(meta.get("stargazers_count") or 0)
    except Exception:
        stars = 0
    lic = meta.get("license") if isinstance(meta.get("license"), dict) else {}
    license_spdx = str(lic.get("spdx_id") or "") if isinstance(lic, dict) else ""

    repo = GithubRepo(
        full_name=full_name,
        html_url=html_url,
        description=description,
        stargazers_count=stars,
        language=language,
        default_branch=default_branch,
        license_spdx=license_spdx,
        pushed_at=str(meta.get("pushed_at") or ""),
    )

    readme = github_fetch_readme_excerpt_raw(full_name=repo.full_name, default_branch=repo.default_branch)
    combined = combine_repo_text(repo, readme)

    debug: dict[str, Any] = {}
    if info is not None:
        info["full_name"] = repo.full_name
        info["default_branch"] = repo.default_branch
        info["stars"] = repo.stargazers_count
        info["language"] = repo.language
        info["license_spdx"] = repo.license_spdx
        info["readme_chars"] = len(readme)
        debug["github"] = info

    final_url = canonicalize_source_url(html_url) or html_url
    return FetchResult(
        raw_html=readme,
        extracted_text=combined,
        final_url=final_url,
        title=repo.full_name,
        platform="github",
        used_playwright=False,
        debug=debug,
    )
