from __future__ import annotations

import os
from typing import Any, List

from .baidu import search_baidu_urls
from .xhs import search_xhs_urls
from .zhihu import search_zhihu_urls

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover - best effort import
    TavilyClient = None  # type: ignore[misc,assignment]

try:
    from ddgs import DDGS  # type: ignore
except Exception:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS  # type: ignore  # legacy name
    except Exception:
        DDGS = None  # type: ignore[misc,assignment]


def search_web_urls_with_tavily(
    topic: str,
    *,
    limit: int = 10,
    search_depth: str = "advanced",
    info: dict[str, Any] | None = None,
) -> list[str]:
    """
    Use Tavily search API to fetch up to `limit` web URLs for the given topic.
    Returns an empty list if Tavily is unavailable or errors occur.
    """
    if not (TavilyClient and (os.environ.get("TAVILY_API_KEY") or os.environ.get("TAVILY_TOKEN"))):
        if info is not None:
            info["enabled"] = False
        return []

    api_key = os.environ.get("TAVILY_API_KEY") or os.environ.get("TAVILY_TOKEN") or ""
    try:
        client = TavilyClient(api_key=api_key)
    except Exception:
        if info is not None:
            info["enabled"] = True
            info["status"] = "client_init_failed"
        return []

    limit = max(1, min(int(limit or 0), 200))  # hard cap to avoid runaway loops
    urls: List[str] = []
    # Tavily max_results is capped at 20; loop until we collect enough or results dry up.
    while len(urls) < limit:
        need = min(20, limit - len(urls))
        try:
            resp: dict[str, Any] = client.search(topic, max_results=need, search_depth=search_depth)  # type: ignore[arg-type]
        except Exception as e:
            if info is not None:
                info["enabled"] = True
                info["status"] = "error"
                info["error"] = f"{type(e).__name__}: {e}"
            break
        results = resp.get("results") if isinstance(resp, dict) else None
        if not isinstance(results, list) or not results:
            break
        added = 0
        for r in results:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url") or "").strip()
            if not url or url in urls:
                continue
            urls.append(url)
            added += 1
            if len(urls) >= limit:
                break
        if added == 0:
            break  # avoid infinite loop if Tavily repeats the same set
    if info is not None and "status" not in info:
        info["enabled"] = True
        info["status"] = "ok" if urls else "empty"
        info["count"] = len(urls)
    return urls


def search_web_urls_with_ddg(
    topic: str,
    *,
    limit: int = 10,
    info: dict[str, Any] | None = None,
) -> list[str]:
    """
    Use DuckDuckGo text search to fetch up to `limit` web URLs.
    Free, no API key required.
    """
    if not DDGS:
        if info is not None:
            info["enabled"] = False
        return []

    limit = max(1, min(int(limit or 0), 200))
    urls: List[str] = []
    try:
        ddgs = DDGS()
        results_list = ddgs.text(topic, max_results=limit)
        for r in results_list:
            url = str(r.get("href") or "").strip()
            if url and url not in urls:
                urls.append(url)
            if len(urls) >= limit:
                break
    except Exception as e:
        if info is not None:
            info["enabled"] = True
            info["status"] = "error"
            info["error"] = f"{type(e).__name__}: {e}"
        return urls

    if info is not None and "status" not in info:
        info["enabled"] = True
        info["status"] = "ok" if urls else "empty"
        info["count"] = len(urls)
    return urls


def search_web_urls(topic: str, *, limit: int = 10, info: dict[str, Any] | None = None) -> list[str]:
    """
    Aggregate web search results from multiple providers (best-effort).

    Provider selection is controlled by `LANGSKILLS_WEB_SEARCH_PROVIDERS`:
      - default: "tavily,baidu,zhihu,xhs"
      - set to "none" to disable search completely.

    Notes:
    - If `LANGSKILLS_OFFLINE=1`, always returns [].
    - Baidu/Zhihu/XHS providers require Playwright + browsers installed.
    - Zhihu/XHS may require interactive login (see LANGSKILLS_ZHIHU_LOGIN_TYPE / LANGSKILLS_XHS_LOGIN_TYPE).
    """
    if str(os.environ.get("LANGSKILLS_OFFLINE") or "").strip() == "1":
        return []

    q = str(topic or "").strip()
    if not q or limit <= 0:
        return []

    raw = str(os.environ.get("LANGSKILLS_WEB_SEARCH_PROVIDERS") or "").strip()
    providers = [x.strip().lower() for x in (raw.split(",") if raw else ["tavily", "ddg", "baidu", "zhihu", "xhs"]) if x.strip()]
    if any(x in {"none", "off", "disable", "disabled"} for x in providers):
        return []

    want = max(1, min(200, int(limit)))
    urls: list[str] = []
    providers_info: dict[str, Any] | None = None
    if info is not None:
        providers_info = {}
        info["providers"] = providers_info
        info["providers_selected"] = providers
    for p in providers:
        if len(urls) >= want:
            break
        if p == "tavily":
            sub: dict[str, Any] = {}
            urls.extend(search_web_urls_with_tavily(q, limit=want, info=sub))
            if providers_info is not None:
                providers_info["tavily"] = sub or {"enabled": True}
        elif p == "ddg":
            sub_ddg: dict[str, Any] = {}
            urls.extend(search_web_urls_with_ddg(q, limit=want, info=sub_ddg))
            if providers_info is not None:
                providers_info["ddg"] = sub_ddg or {"enabled": True}
        elif p == "baidu":
            urls.extend(search_baidu_urls(q, limit=want))
            if providers_info is not None:
                providers_info["baidu"] = {"enabled": True}
        elif p == "zhihu":
            sub: dict[str, Any] = {}
            urls.extend(search_zhihu_urls(q, limit=want, info=sub if info is not None else None))
            if providers_info is not None:
                providers_info["zhihu"] = sub or {"enabled": True}
        elif p == "xhs":
            sub = {}
            urls.extend(search_xhs_urls(q, limit=want, info=sub if info is not None else None))
            if providers_info is not None:
                providers_info["xhs"] = sub or {"enabled": True}

    # Dedupe while preserving order.
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        s = str(u or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= want:
            break
    return out
