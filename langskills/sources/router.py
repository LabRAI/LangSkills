from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlsplit

from .types import FetchResult
from .arxiv import fetch_arxiv_text
from .github import fetch_github_text
from .stackoverflow import fetch_stackoverflow_text
from .webpage import fetch_webpage_text
from .xhs import fetch_xhs_text
from .zhihu import fetch_zhihu_text


def detect_fetch_engine(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return "webpage"
    try:
        host = str(urlsplit(u).hostname or "").strip().lower()
        path = str(urlsplit(u).path or "")
    except Exception:
        host = ""
        path = ""
    if host == "zhihu.com" or host.endswith(".zhihu.com"):
        return "zhihu"
    if host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com"):
        return "xhs"
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if host == "stackoverflow.com" or host.endswith(".stackoverflow.com"):
        return "forum"
    if host == "arxiv.org" or host.endswith(".arxiv.org"):
        if path.startswith("/abs/") or path.startswith("/pdf/"):
            return "arxiv"
    return "webpage"


def fetch_text(
    url: str,
    *,
    engine: str = "auto",
    timeout_ms: int = 25_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> FetchResult:
    """
    Unified fetch entrypoint for debugging and pipelines.

    Engines:
    - auto: route by hostname
    - webpage: best-effort HTTP (+ optional Playwright fallback for some cases)
    - github: repo description + README excerpt (best-effort)
    - forum: StackOverflow question + best answer (best-effort)
    - arxiv: title + abstract via arXiv API
    - zhihu: Playwright + login/verification handling
    - xhs: Playwright + login/verification handling
    """
    eng = str(engine or "").strip().lower()
    if eng in {"", "auto"}:
        eng = detect_fetch_engine(url)
    if eng in {"webpage", "web", "http", "baidu"}:
        return fetch_webpage_text(url, timeout_ms=timeout_ms)
    if eng == "github":
        return fetch_github_text(url, timeout_ms=timeout_ms, info=info)
    if eng in {"forum", "stackoverflow"}:
        return fetch_stackoverflow_text(url, timeout_ms=timeout_ms, info=info, emit=emit)
    if eng == "arxiv":
        return fetch_arxiv_text(url, timeout_ms=timeout_ms, info=info)
    if eng == "zhihu":
        return fetch_zhihu_text(url, timeout_ms=timeout_ms, info=info, emit=emit)
    if eng == "xhs":
        return fetch_xhs_text(url, timeout_ms=timeout_ms, info=info, emit=emit)
    raise ValueError(f"Unknown fetch engine: {engine}")
