from __future__ import annotations

import os
import re
import time
from typing import Any, Callable
from urllib.parse import quote

from ..config import extract_url_hostname
from ..env import env_bool as _env_bool
from ..env import env_int as _env_int
from ..utils.iterables import dedupe_strs
from ..utils.text import html_to_text
from .playwright_utils import add_cookie_string, cookies_as_dict, playwright_available, playwright_page, resolve_auth_dir, wait_until
from .types import FetchResult

_ZHIHU_QR_ALT = "\u4e8c\u7ef4\u7801"


def _convert_zhihu_api_url(raw_url: str, *, answer_question_id: str | None = None) -> str:
    u = str(raw_url or "").strip()
    if not u:
        return ""
    m = re.match(r"^https?://api\\.zhihu\\.com/questions/(\\d+)", u)
    if m:
        return f"https://www.zhihu.com/question/{m.group(1)}"
    m = re.match(r"^https?://api\\.zhihu\\.com/articles/(\\d+)", u)
    if m:
        return f"https://zhuanlan.zhihu.com/p/{m.group(1)}"
    m = re.match(r"^https?://api\\.zhihu\\.com/answers/(\\d+)", u)
    if m and answer_question_id:
        return f"https://www.zhihu.com/question/{answer_question_id}/answer/{m.group(1)}"
    return u


def _urls_from_search_v3(data: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(data, dict):
        return out
    items = data.get("data")
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        obj = item.get("object") if isinstance(item.get("object"), dict) else None
        if obj:
            obj_type = str(obj.get("type") or "").strip().lower()
            if obj_type == "answer":
                aid = str(obj.get("id") or "").strip()
                qobj = obj.get("question") if isinstance(obj.get("question"), dict) else None
                qid = str(qobj.get("id") or "").strip() if qobj else ""
                if aid and qid:
                    out.append(f"https://www.zhihu.com/question/{qid}/answer/{aid}")
                    continue
            if obj_type == "question":
                qid = str(obj.get("id") or obj.get("url_token") or "").strip()
                if qid:
                    out.append(f"https://www.zhihu.com/question/{qid}")
                    continue
            if obj_type == "article":
                aid = str(obj.get("id") or "").strip()
                if aid:
                    out.append(f"https://zhuanlan.zhihu.com/p/{aid}")
                    continue
            if obj_type == "zvideo":
                vid = str(obj.get("id") or obj.get("url_token") or "").strip()
                if vid:
                    out.append(f"https://www.zhihu.com/zvideo/{vid}")
                    continue
            qobj = obj.get("question") if isinstance(obj.get("question"), dict) else None
            qid = str(qobj.get("id") or "").strip() if qobj else ""
            u = _convert_zhihu_api_url(str(obj.get("url") or ""), answer_question_id=qid or None)
            if u:
                out.append(u)
        else:
            u = str(item.get("url") or "").strip()
            if u:
                out.append(u)
    return out


def _fetch_search_v3_urls(page: Any, *, query: str, limit: int, timeout_ms: int) -> list[str]:
    q = str(query or "").strip()
    if not q:
        return []
    per_page = max(1, min(20, int(limit)))
    max_pages = max(1, min(10, (int(limit) + per_page - 1) // per_page))
    collected: list[str] = []
    seen: set[str] = set()
    for i in range(max_pages):
        offset = i * per_page
        api = (
            "https://www.zhihu.com/api/v4/search_v3"
            f"?t=general&q={quote(q)}&correction=1&offset={offset}&limit={per_page}"
        )
        try:
            data = page.evaluate(
                """
                async (api) => {
                  const resp = await fetch(api, {credentials: 'include'});
                  if (!resp.ok) { return {error: resp.status}; }
                  return await resp.json();
                }
                """,
                api,
            )
        except Exception:
            break
        urls = _urls_from_search_v3(data)
        if not urls:
            break
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                collected.append(u)
        if len(collected) >= limit:
            break
        try:
            page.wait_for_timeout(max(200, min(800, int(timeout_ms) // 50)))
        except Exception:
            time.sleep(0.2)
    return dedupe_strs(collected)


def zhihu_login_type() -> str:
    return str(os.environ.get("LANGSKILLS_ZHIHU_LOGIN_TYPE") or "qrcode").strip().lower()


def zhihu_requires_headful(login_type: str | None = None) -> bool:
    t = str(login_type or zhihu_login_type()).strip().lower()
    return t in {"qrcode", "phone"}


def _is_logged_in(page: Any) -> bool:
    cookie_dict = cookies_as_dict(page.context)
    return bool(str(cookie_dict.get("z_c0") or "").strip())


def _maybe_handle_unhuman(page: Any, emit: Callable[[str], None] | None) -> bool:
    try:
        if page.locator("section.Unhuman-verificationCode, .Unhuman").count() <= 0:
            return False
    except Exception:
        return False
    if emit:
        emit("[langskills] Zhihu anti-bot verification detected; please complete verification in the opened browser window.")
    try:
        page.locator("button.Unhuman-confirm").first.click()
    except Exception:
        pass
    try:
        page.locator("a.Unhuman-login").first.click()
    except Exception:
        pass
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    return True


def ensure_zhihu_login(
    page: Any,
    *,
    timeout_sec: int | None = None,
    return_url: str | None = None,
    emit: Callable[[str], None] | None = print,
    info: dict[str, Any] | None = None,
    headless: bool | None = None,
) -> bool:
    """
    Ensure the page's context is logged in to Zhihu, using the same login types as the reference:
    - qrcode: scan QR code (manual verification if prompted)
    - cookie: set cookies from LANGSKILLS_ZHIHU_COOKIES
    - phone: placeholder (not implemented in reference either)
    """
    if _is_logged_in(page):
        if info is not None:
            info["login_ok"] = True
        return True

    login_type = zhihu_login_type()
    timeout_sec = int(timeout_sec or _env_int("LANGSKILLS_ZHIHU_LOGIN_TIMEOUT_SEC", 120))
    if info is not None:
        info["login_type"] = login_type

    if login_type == "cookie":
        add_cookie_string(page, str(os.environ.get("LANGSKILLS_ZHIHU_COOKIES") or ""), domain=".zhihu.com")
        # Verify.
        try:
            page.goto("https://www.zhihu.com/", wait_until="domcontentloaded")
        except Exception:
            pass
        ok = _is_logged_in(page)
        if info is not None:
            info["login_ok"] = bool(ok)
        if ok and return_url:
            try:
                page.goto(return_url, wait_until="domcontentloaded")
            except Exception:
                pass
        return ok

    if login_type == "phone":
        raise RuntimeError("Zhihu phone login is not implemented (same as reference). Use qrcode or cookie.")

    if login_type != "qrcode":
        raise RuntimeError(f"Unknown Zhihu login type: {login_type} (expected qrcode|cookie|phone)")

    if headless is None:
        headless = _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)
    if bool(headless):
        if info is not None:
            info["login_ok"] = False
            info["requires_headful"] = True
        if emit:
            emit(
                "[langskills] Zhihu QR login requires a visible browser. "
                "Run `python3 langskills_cli.py auth zhihu` (or set LANGSKILLS_PLAYWRIGHT_HEADLESS=0) once to persist the session."
            )
        return False

    # Force a deterministic login page (Zhihu often defaults to QR code here).
    page.goto("https://www.zhihu.com/signin?next=%2F", wait_until="domcontentloaded")
    _maybe_handle_unhuman(page, emit)
    qr_selectors = [
        "canvas.Qrcode-qrcode",
        "canvas[class*='Qrcode']",
        "img[class*='Qrcode']",
        "img[src*='qrcode']",
        f"img[alt*='{_ZHIHU_QR_ALT}']",
    ]
    qr_selector = ", ".join(qr_selectors)
    try:
        page.wait_for_selector(qr_selector, timeout=15_000)
    except Exception as e:
        raise RuntimeError("Zhihu login QR code not found.") from e

    auth_dir = resolve_auth_dir()
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    qr_path = auth_dir / f"zhihu_qrcode_{ts}.png"
    try:
        locator = None
        for sel in qr_selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    locator = loc.first
                    break
            except Exception:
                continue
        if locator is None:
            raise RuntimeError("Zhihu login QR code not found.")
        locator.screenshot(path=str(qr_path))
        if info is not None:
            info["qrcode_path"] = qr_path.as_posix()
        if emit:
            emit(f"[langskills] Zhihu QR code saved: {qr_path.as_posix()}")
    except Exception:
        # If we cannot capture the QR code, still allow manual login in the opened page.
        if info is not None:
            info["qrcode_error"] = "capture_failed"
        if emit:
            emit("[langskills] Zhihu QR code capture failed; please complete login in the opened browser window.")

    ok = wait_until(predicate=lambda: _is_logged_in(page), timeout_sec=timeout_sec, poll_sec=1.0)
    if info is not None:
        info["login_ok"] = bool(ok)
    if not ok:
        return False

    # Give Zhihu a moment to redirect/settle.
    time.sleep(5)
    if return_url:
        try:
            page.goto(return_url, wait_until="domcontentloaded")
        except Exception:
            pass
    return True


def search_zhihu_urls(
    query: str,
    *,
    limit: int = 10,
    timeout_ms: int = 25_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[str]:
    """
    Best-effort Zhihu search via Playwright.

    If login is needed, this will follow LANGSKILLS_ZHIHU_LOGIN_TYPE:
    - qrcode: open a browser and wait for scan
    - cookie: set cookies from LANGSKILLS_ZHIHU_COOKIES
    """
    q = str(query or "").strip()
    if not q or limit <= 0:
        return []
    if not playwright_available():
        return []

    url = f"https://www.zhihu.com/search?type=content&q={quote(q)}"
    try:
        # Do not force headful just because login_type is qrcode/phone:
        # if the persistent browser profile is already logged in, headless mode should work.
        # When interactive login is required, callers should run `langskills auth zhihu` with a visible browser once.
        with playwright_page(platform="zhihu", timeout_ms=timeout_ms, headless=None) as page:
            headless = _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)
            if not ensure_zhihu_login(page, return_url=url, emit=emit, info=info, headless=headless):
                return []

            page.goto(url, wait_until="domcontentloaded")
            selector = "a[href*='/question/'], a[href*='/p/'], a[href*='/answer/']"
            try:
                page.wait_for_selector(selector, timeout=timeout_ms)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:
                pass

            cleaned: list[str] = []
            seen: set[str] = set()

            def _collect() -> None:
                hrefs = page.eval_on_selector_all(selector, "els => els.map(e => e.href)")  # type: ignore[no-untyped-call]
                if not isinstance(hrefs, list):
                    return
                for h in hrefs:
                    u = str(h or "").strip()
                    if not u.startswith("http"):
                        continue
                    host = extract_url_hostname(u)
                    if host and host.endswith("zhihu.com") and u not in seen:
                        seen.add(u)
                        cleaned.append(u)

            _collect()
            max_scrolls = max(2, min(10, 1 + (limit // 5)))
            stagnant = 0
            for _ in range(max_scrolls):
                if len(cleaned) >= limit:
                    break
                try:
                    page.mouse.wheel(0, 2500)
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(1000)
                except Exception:
                    time.sleep(1)
                before = len(cleaned)
                _collect()
                if len(cleaned) == before:
                    stagnant += 1
                    if stagnant >= 2:
                        break
                else:
                    stagnant = 0

            if len(cleaned) < limit:
                api_urls = _fetch_search_v3_urls(page, query=q, limit=limit, timeout_ms=timeout_ms)
                for u in api_urls:
                    host = extract_url_hostname(u)
                    if host and host.endswith("zhihu.com") and u not in seen:
                        seen.add(u)
                        cleaned.append(u)

            return dedupe_strs(cleaned)[: max(1, min(200, int(limit)))]
    except Exception:
        return []


_VERIFY_MARKERS = (
    "\u7f51\u7edc\u73af\u5883\u5b58\u5728\u5f02\u5e38",
    "\u8bf7\u70b9\u51fb\u4e0b\u65b9\u9a8c\u8bc1\u6309\u94ae\u8fdb\u884c\u9a8c\u8bc1",
    "\u5b8c\u6210\u9a8c\u8bc1",
    "\u9a8c\u8bc1\u6309\u94ae",
)


def _page_needs_verification(page: Any) -> bool:
    html = ""
    try:
        html = str(page.content() or "")
    except Exception:
        html = ""
    if html:
        sample = html[:20000]
        if any(marker in sample for marker in _VERIFY_MARKERS):
            return True

    text = ""
    try:
        text = str(page.inner_text("body") or "")
    except Exception:
        text = ""
    if text:
        sample = text[:20000]
        if any(marker in sample for marker in _VERIFY_MARKERS):
            return True
    return False


def _effective_headless(headless_override: bool | None) -> bool:
    if headless_override is not None:
        return bool(headless_override)
    return _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)


def _wait_for_manual_verification(
    page: Any,
    *,
    headless: bool,
    timeout_sec: int,
    emit: Callable[[str], None] | None,
) -> None:
    if headless:
        raise RuntimeError(
            "Zhihu requires human verification. Re-run with a visible browser "
            "(set LANGSKILLS_PLAYWRIGHT_HEADLESS=0) and complete the verification once."
        )

    deadline = time.time() + max(5, int(timeout_sec))
    if emit:
        emit(f"[langskills] Zhihu requires verification; please complete it in the opened browser (timeout {timeout_sec}s).")
    try:
        page.bring_to_front()
    except Exception:
        pass

    while time.time() < deadline:
        if not _page_needs_verification(page):
            return
        time.sleep(2)
    raise RuntimeError(f"Zhihu verification not completed within {timeout_sec}s.")


def fetch_zhihu_text(
    url: str,
    *,
    timeout_ms: int = 25_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> FetchResult:
    """
    Fetch a Zhihu page via Playwright, with optional login (cookie/qrcode) + human-verification handling.
    """
    u = str(url or "").strip()
    if not u:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="zhihu", used_playwright=False)
    if not playwright_available():
        raise RuntimeError("Playwright is not available. Install it and run `playwright install chromium`.")

    headless_override: bool | None = None
    is_headless = _effective_headless(headless_override)

    with playwright_page(platform="zhihu", timeout_ms=timeout_ms, headless=headless_override) as page:
        if not ensure_zhihu_login(page, return_url=u, emit=emit, info=info, headless=is_headless):
            raise RuntimeError("Zhihu login failed.")

        if _page_needs_verification(page):
            auth_dir = resolve_auth_dir()
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            shot = auth_dir / f"zhihu_verify_{ts}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                if info is not None:
                    info["verification_screenshot"] = shot.as_posix()
            except Exception:
                pass

            timeout_sec = int(_env_int("LANGSKILLS_ZHIHU_VERIFY_TIMEOUT_SEC", 600))
            _wait_for_manual_verification(page, headless=is_headless, timeout_sec=timeout_sec, emit=emit)
            try:
                page.goto(u, wait_until="domcontentloaded")
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        html = ""
        last_err: Exception | None = None
        for _ in range(0, 6):
            try:
                html = str(page.content() or "")
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

        final_url = str(getattr(page, "url", "") or "").strip() or u
        title = ""
        try:
            title = str(page.title() or "").strip()
        except Exception:
            title = ""

        extracted = html_to_text(html)
        if len(str(extracted or "").strip()) < 200:
            try:
                body_text = str(page.inner_text("body") or "")
                if len(body_text.strip()) > len(str(extracted or "").strip()):
                    extracted = body_text
            except Exception:
                pass

        debug: dict[str, Any] = {}
        if info is not None:
            debug["auth"] = info
        return FetchResult(
            raw_html=html,
            extracted_text=str(extracted or ""),
            final_url=final_url,
            title=title,
            platform="zhihu",
            used_playwright=True,
            debug=debug,
        )
