from __future__ import annotations

from urllib.parse import quote

from .playwright_utils import playwright_available, playwright_page
from ..utils.iterables import dedupe_strs


def search_baidu_urls(query: str, *, limit: int = 10, timeout_ms: int = 25_000) -> list[str]:
    """
    Best-effort Baidu search via Playwright.

    Returns a list of URLs (may include Baidu redirect links).
    """
    q = str(query or "").strip()
    if not q or limit <= 0:
        return []
    if not playwright_available():
        return []

    url = f"https://www.baidu.com/s?wd={quote(q)}"
    try:
        with playwright_page(platform="baidu", timeout_ms=timeout_ms) as page:
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("#content_left", timeout=timeout_ms)
            except Exception:
                pass
            hrefs = page.eval_on_selector_all("#content_left h3 a[href]", "els => els.map(e => e.href)")  # type: ignore[no-untyped-call]
            if not isinstance(hrefs, list):
                return []
            cleaned = [str(x) for x in hrefs if str(x).strip().startswith("http")]
            return dedupe_strs(cleaned)[: max(1, min(200, int(limit)))]
    except Exception:
        return []
