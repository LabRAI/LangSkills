from __future__ import annotations

import time
from urllib.parse import urlsplit

from ..env import env_bool as _env_bool
from ..utils.http import HttpError, fetch_with_retries
from ..utils.text import html_to_text
from .playwright_utils import playwright_available, playwright_page
from .types import FetchResult


def _looks_like_cloudflare_challenge(*, raw_html: str, extracted_text: str) -> bool:
    t = str(extracted_text or "").strip().lower()
    if not t:
        return False
    if t == "just a moment..." or t.startswith("just a moment"):
        return True
    h = str(raw_html or "").lower()
    if "/cdn-cgi/" in h and ("challenge" in h or "cf-chl" in h):
        return True
    if "checking your browser" in t and "/cdn-cgi/" in h:
        return True
    return False


def is_baidu_redirect_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        parts = urlsplit(u)
    except Exception:
        return False
    host = str(parts.hostname or "").lower()
    path = str(parts.path or "")
    if not (host == "www.baidu.com" or host.endswith(".baidu.com")):
        return False
    # Baidu frequently returns redirect wrappers like:
    # - https://www.baidu.com/link?url=...
    # - https://www.baidu.com/baidu.php?url=...
    if path.startswith("/link"):
        return True
    if path == "/baidu.php" or path.startswith("/baidu.php/"):
        return True
    return False


def is_stackoverflow_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        parts = urlsplit(u)
    except Exception:
        return False
    host = str(parts.hostname or "").lower()
    return host == "stackoverflow.com" or host.endswith(".stackoverflow.com")


def fetch_webpage_text(url: str, *, timeout_ms: int = 25_000, retries: int = 2) -> FetchResult:
    """
    Fetch a web page and return both raw HTML (or plain text) and extracted text.
    """
    u = str(url or "").strip()
    if not u:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="", used_playwright=False)

    def should_try_playwright(err: Exception) -> bool:
        if _env_bool("LANGSKILLS_PLAYWRIGHT_WEBPAGE_FALLBACK", False):
            return True
        if is_baidu_redirect_url(u):
            return True
        # StackOverflow occasionally fails with transient network/SSL errors under urllib;
        # Playwright is typically more reliable for these pages.
        if is_stackoverflow_url(u):
            return True
        if isinstance(err, HttpError) and int(getattr(err, "status", 0) or 0) in {403, 429, 521}:
            return True
        return False

    try:
        resp = fetch_with_retries(u, timeout_ms=timeout_ms, retries=retries, accept="text/html,*/*")
        extracted = html_to_text(resp.text)
        if is_stackoverflow_url(u) and _looks_like_cloudflare_challenge(raw_html=resp.text, extracted_text=extracted):
            raise RuntimeError("cloudflare_challenge")
        out = FetchResult(raw_html=resp.text, extracted_text=extracted, final_url=u, platform="http", used_playwright=False)

        # Baidu redirect wrapper pages often return HTML that doesn't contain the final target content.
        # Resolve with Playwright even when the plain HTTP fetch succeeds.
        if playwright_available() and is_baidu_redirect_url(u) and len(str(extracted or "").strip()) < 200:
            try:
                with playwright_page(platform="baidu", timeout_ms=timeout_ms) as page:
                    page.goto(u, wait_until="domcontentloaded")
                    html = str(page.content() or "")
                    final_url = str(getattr(page, "url", "") or "").strip() or u
                    title = ""
                    try:
                        title = str(page.title() or "").strip()
                    except Exception:
                        title = ""
                    extracted2 = html_to_text(html)
                    return FetchResult(
                        raw_html=html,
                        extracted_text=extracted2,
                        final_url=final_url,
                        title=title,
                        platform="baidu",
                        used_playwright=True,
                    )
            except Exception:
                return out

        return out
    except Exception as e:
        if not should_try_playwright(e) or not playwright_available():
            raise

        platform = "baidu" if is_baidu_redirect_url(u) else "webpage"
        try:
            with playwright_page(platform=platform, timeout_ms=timeout_ms) as page:
                page.goto(u, wait_until="domcontentloaded")
                html = ""
                extracted = ""
                last_err: Exception | None = None
                for _ in range(0, 10):
                    try:
                        html = str(page.content() or "")
                        extracted = html_to_text(html)
                        if is_stackoverflow_url(u) and _looks_like_cloudflare_challenge(raw_html=html, extracted_text=extracted):
                            try:
                                page.wait_for_timeout(1000)
                            except Exception:
                                pass
                            time.sleep(0.1)
                            continue
                        break
                    except Exception as err:
                        last_err = err
                        try:
                            page.wait_for_timeout(500)
                        except Exception:
                            pass
                        time.sleep(0.1)
                if not html and last_err:
                    raise last_err
                if is_stackoverflow_url(u) and _looks_like_cloudflare_challenge(raw_html=html, extracted_text=extracted):
                    raise RuntimeError("cloudflare_challenge")
                final_url = str(getattr(page, "url", "") or "").strip() or u
                title = ""
                try:
                    title = str(page.title() or "").strip()
                except Exception:
                    title = ""
                return FetchResult(
                    raw_html=html,
                    extracted_text=extracted,
                    final_url=final_url,
                    title=title,
                    platform=platform,
                    used_playwright=True,
                )
        except Exception:
            raise
