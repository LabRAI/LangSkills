from __future__ import annotations

import os
import sys
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

_XHS_LOGIN_TEXT = "\u767b\u5f55"
_XHS_VERIFY_PROMPT = "\u8bf7\u901a\u8fc7\u9a8c\u8bc1"
_XHS_SECURITY_VERIFICATION = "\u5b89\u5168\u9a8c\u8bc1"


def xhs_login_type() -> str:
    return str(os.environ.get("LANGSKILLS_XHS_LOGIN_TYPE") or "qrcode").strip().lower()


def xhs_requires_headful(login_type: str | None = None) -> bool:
    t = str(login_type or xhs_login_type()).strip().lower()
    return t in {"qrcode", "phone"}


def _web_session(page: Any) -> str:
    cookie_dict = cookies_as_dict(page.context)
    return str(cookie_dict.get("web_session") or "").strip()


def _qrcode_visible(page: Any) -> bool:
    try:
        return int(page.locator("img.qrcode-img").count()) > 0
    except Exception:
        return False


def _login_button_visible(page: Any) -> bool:
    try:
        loc = page.locator(f'button:has-text("{_XHS_LOGIN_TEXT}")')
        if int(loc.count()) <= 0:
            return False
        try:
            return bool(loc.first.is_visible())
        except Exception:
            return True
    except Exception:
        return False


def ensure_xhs_login(
    page: Any,
    *,
    timeout_sec: int | None = None,
    return_url: str | None = None,
    emit: Callable[[str], None] | None = print,
    info: dict[str, Any] | None = None,
    headless: bool | None = None,
) -> bool:
    """
    Ensure the page's context is logged in to Xiaohongshu (XHS), using the same login types as the reference:
    - qrcode: scan QR code (manual CAPTCHA/slider verification if prompted)
    - cookie: set web_session from LANGSKILLS_XHS_COOKIES
    - phone: placeholder (supported in reference; requires external SMS code injection)
    """
    login_type = xhs_login_type()
    timeout_sec = int(timeout_sec or _env_int("LANGSKILLS_XHS_LOGIN_TIMEOUT_SEC", 120))
    if info is not None:
        info["login_type"] = login_type

    if login_type == "cookie":
        add_cookie_string(
            page,
            str(os.environ.get("LANGSKILLS_XHS_COOKIES") or ""),
            domain=".xiaohongshu.com",
            allow_keys={"web_session"},
        )
        try:
            page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
        except Exception:
            pass
        ok = bool(_web_session(page))
        if info is not None:
            info["login_ok"] = bool(ok)
        if ok and return_url:
            try:
                page.goto(return_url, wait_until="domcontentloaded")
            except Exception:
                pass
        return ok

    if login_type == "phone":
        phone = str(os.environ.get("LANGSKILLS_XHS_PHONE") or "").strip()
        if not phone:
            raise RuntimeError("XHS phone login requires LANGSKILLS_XHS_PHONE.")

        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")

        # Bring up login modal, then switch to phone login.
        try:
            login_button = page.locator("xpath=//*[@id='app']/div[1]/div[2]/div[1]/ul/div[1]/button").first
            login_button.click()
        except Exception:
            pass
        try:
            other_method = page.locator("xpath=//div[@class='login-container']//div[@class='other-method']/div[1]").first
            other_method.click()
        except Exception:
            pass

        page.wait_for_selector("div.login-container", timeout=15_000)
        login_container = page.locator("div.login-container").first
        login_container.locator("label.phone > input").first.fill(phone)
        time.sleep(0.5)

        # Send SMS code and wait for it.
        try:
            login_container.locator("label.auth-code > span").first.click()
        except Exception:
            pass

        sms_code = str(os.environ.get("LANGSKILLS_XHS_SMS_CODE") or "").strip()
        if not sms_code:
            if sys.stdin is None or not sys.stdin.isatty():
                raise RuntimeError("XHS phone login requires LANGSKILLS_XHS_SMS_CODE in non-interactive mode.")
            sms_code = input(f"Enter XHS SMS code for {phone}: ").strip()

        # Capture baseline session after sending code (matches reference logic).
        baseline = _web_session(page)

        login_container.locator("label.auth-code > input").first.fill(sms_code)
        time.sleep(0.5)
        try:
            page.locator("xpath=//div[@class='agreements']//*[local-name()='svg']").first.click()
        except Exception:
            pass
        time.sleep(0.5)
        try:
            login_container.locator("div.input-container > button").first.click()
        except Exception:
            pass

        ok = wait_until(predicate=lambda: bool(_web_session(page)) and _web_session(page) != baseline, timeout_sec=timeout_sec, poll_sec=1.0)
        if info is not None:
            info["login_ok"] = bool(ok)
        if not ok:
            return False

        time.sleep(5)
        if return_url:
            try:
                page.goto(return_url, wait_until="domcontentloaded")
            except Exception:
                pass
        return True

    if login_type != "qrcode":
        raise RuntimeError(f"Unknown XHS login type: {login_type} (expected qrcode|cookie|phone)")

    if headless is None:
        headless = _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)
    if bool(headless):
        # In headless mode we cannot complete QR-code login. If a persistent profile already has a session
        # cookie, proceed best-effort; otherwise fail fast (so bulk crawls don't stall on login).
        if _web_session(page):
            if info is not None:
                info["login_ok"] = True
                info["login_ok_via"] = "cookie:web_session"
            if return_url:
                try:
                    page.goto(return_url, wait_until="domcontentloaded")
                except Exception:
                    pass
            return True

        if info is not None:
            info["login_ok"] = False
            info["requires_headful"] = True
        if emit:
            emit(
                "[langskills] XHS QR login requires a visible browser. "
                "Run `python3 langskills_cli.py auth xhs` (or set LANGSKILLS_PLAYWRIGHT_HEADLESS=0) once to persist the session."
            )
        return False

    # Use a page that reliably requires login; if already logged in, QR code won't appear.
    page.goto("https://www.xiaohongshu.com/user/profile/me", wait_until="domcontentloaded")

    # Already logged in: no QR code is shown, and the global login button is absent.
    if not _login_button_visible(page) and not _qrcode_visible(page):
        if info is not None:
            info["login_ok"] = True
        if return_url:
            try:
                page.goto(return_url, wait_until="domcontentloaded")
            except Exception:
                pass
        return True

    # XHS can have a web_session cookie even when not logged in; keep baseline for best-effort detection.
    baseline = _web_session(page)

    # Try to bring up login modal if needed.
    if not _qrcode_visible(page):
        try:
            page.locator(f'button:has-text("{_XHS_LOGIN_TEXT}")').first.click()
        except Exception:
            try:
                login_button = page.locator("xpath=//*[@id='app']/div[1]/div[2]/div[1]/ul/div[1]/button").first
                login_button.click()
            except Exception:
                pass

        try:
            page.wait_for_selector("img.qrcode-img", timeout=15_000)
        except Exception:
            if emit:
                emit("[langskills] XHS login UI not detected; please complete login manually in the opened browser window.")

    # Capture baseline again after login UI is (possibly) opened; some flows set web_session lazily.
    baseline2 = _web_session(page)
    if baseline2:
        baseline = baseline2

    auth_dir = resolve_auth_dir()
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    qr_path = auth_dir / f"xhs_qrcode_{ts}.png"
    try:
        locator = page.locator("img.qrcode-img").first
        locator.screenshot(path=str(qr_path))
        if info is not None:
            info["qrcode_path"] = qr_path.as_posix()
        if emit:
            emit(f"[langskills] XHS QR code saved: {qr_path.as_posix()}")
    except Exception:
        if info is not None:
            info["qrcode_error"] = "capture_failed"
        if emit:
            emit("[langskills] XHS QR code capture failed; please complete login in the opened browser window.")

    def _logged_in() -> bool:
        # During login, XHS may show CAPTCHA; the user needs to pass it manually.
        try:
            if _XHS_VERIFY_PROMPT in str(page.content() or ""):
                if emit:
                    emit("[langskills] XHS CAPTCHA detected: please verify manually in the opened browser window.")
        except Exception:
            pass
        if _login_button_visible(page):
            return False
        if not _qrcode_visible(page):
            return True
        cur = _web_session(page)
        return bool(cur) and cur != baseline

    ok = wait_until(predicate=_logged_in, timeout_sec=timeout_sec, poll_sec=1.0)
    if info is not None:
        info["login_ok"] = bool(ok)
    if not ok:
        return False

    time.sleep(5)
    if return_url:
        try:
            page.goto(return_url, wait_until="domcontentloaded")
        except Exception:
            pass
    return True


def search_xhs_urls(
    query: str,
    *,
    limit: int = 10,
    timeout_ms: int = 25_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[str]:
    """
    Best-effort Xiaohongshu (XHS) search via Playwright.

    If login is needed, this will follow LANGSKILLS_XHS_LOGIN_TYPE:
    - qrcode: open a browser and wait for scan (may require manual CAPTCHA verification)
    - cookie: set web_session from LANGSKILLS_XHS_COOKIES
    """
    q = str(query or "").strip()
    if not q or limit <= 0:
        return []
    if not playwright_available():
        return []

    url = f"https://www.xiaohongshu.com/search_result?keyword={quote(q)}"
    try:
        # Do not force headful just because login_type is qrcode/phone:
        # if the persistent browser profile is already logged in, headless mode should work.
        # When interactive login is required, callers should run `langskills auth xhs` with a visible browser once.
        with playwright_page(platform="xhs", timeout_ms=timeout_ms, headless=None) as page:
            headless = _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)
            if not ensure_xhs_login(page, return_url=url, emit=emit, info=info, headless=headless):
                return []

            if _page_needs_verification(page):
                if info is not None:
                    info["captcha_detected"] = True
                    info["captcha_url"] = str(getattr(page, "url", "") or "")
                    try:
                        auth_dir = resolve_auth_dir()
                        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                        shot = auth_dir / f"xhs_search_captcha_{ts}.png"
                        page.screenshot(path=str(shot), full_page=True)
                        info["captcha_screenshot"] = shot.as_posix()
                    except Exception:
                        pass
                return []

            page.goto(url, wait_until="domcontentloaded")

            # Fast-fail on CAPTCHA / login walls to keep bulk runs from stalling.
            if _page_needs_verification(page):
                if info is not None:
                    info["captcha_detected"] = True
                    info["captcha_url"] = str(getattr(page, "url", "") or "")
                    try:
                        auth_dir = resolve_auth_dir()
                        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                        shot = auth_dir / f"xhs_search_captcha_{ts}.png"
                        page.screenshot(path=str(shot), full_page=True)
                        info["captcha_screenshot"] = shot.as_posix()
                    except Exception:
                        pass
                return []
            if _login_button_visible(page) or _qrcode_visible(page):
                if info is not None:
                    info["login_ui_detected"] = True
                    info["login_ok"] = False
                return []

            selector = "a[href*='/explore/'], a[href*='/discovery/item/']"
            try:
                wait_ms = min(timeout_ms, _env_int("LANGSKILLS_XHS_SEARCH_WAIT_TIMEOUT_MS", 8_000))
                page.wait_for_selector(selector, timeout=wait_ms)
            except Exception:
                pass

            # Some accounts get redirected to a verification page after initial render; re-check after waiting.
            if _page_needs_verification(page):
                if info is not None:
                    info["captcha_detected"] = True
                    info["captcha_url"] = str(getattr(page, "url", "") or "")
                return []
            hrefs = page.eval_on_selector_all(selector, "els => els.map(e => e.href)")  # type: ignore[no-untyped-call]
            if not isinstance(hrefs, list):
                if info is not None:
                    try:
                        auth_dir = resolve_auth_dir()
                        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                        shot = auth_dir / f"xhs_search_debug_{ts}.png"
                        page.screenshot(path=str(shot), full_page=True)
                        info["debug_screenshot"] = shot.as_posix()
                    except Exception:
                        pass
                return []
            cleaned: list[str] = []
            for h in hrefs:
                u = str(h or "").strip()
                if not u.startswith("http"):
                    continue
                host = extract_url_hostname(u)
                if host and host.endswith("xiaohongshu.com"):
                    cleaned.append(u)

            if not cleaned and info is not None:
                try:
                    auth_dir = resolve_auth_dir()
                    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                    shot = auth_dir / f"xhs_search_empty_{ts}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    info["empty_screenshot"] = shot.as_posix()
                    info["page_url"] = str(getattr(page, "url", "") or "")
                    try:
                        info["page_title"] = str(page.title() or "")
                    except Exception:
                        pass
                except Exception:
                    pass
            return dedupe_strs(cleaned)[: max(1, min(200, int(limit)))]
    except Exception:
        return []


def _effective_headless(headless_override: bool | None) -> bool:
    if headless_override is not None:
        return bool(headless_override)
    return _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)


def _page_needs_verification(page: Any) -> bool:
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if "/website-login/captcha" in url:
        return True
    if "verifytype=" in url.lower() or "verifyuuid=" in url.lower():
        return True

    try:
        title = str(page.title() or "")
    except Exception:
        title = ""
    if _XHS_SECURITY_VERIFICATION in title:
        return True
    if "captcha" in title.lower():
        return True

    try:
        sample = str(page.content() or "")[:20000]
    except Exception:
        sample = ""
    if _XHS_VERIFY_PROMPT in sample:
        return True
    if _XHS_SECURITY_VERIFICATION in sample:
        return True
    if "verifyType" in sample or "verifyUuid" in sample:
        return True
    if "captcha" in sample.lower():
        return True
    return False


def _wait_for_manual_verification(
    page: Any,
    *,
    headless: bool,
    timeout_sec: int,
    emit: Callable[[str], None] | None,
) -> None:
    if headless:
        raise RuntimeError(
            "XHS requires human verification (CAPTCHA). Re-run with a visible browser "
            "(set LANGSKILLS_PLAYWRIGHT_HEADLESS=0) and complete the verification once."
        )
    deadline = time.time() + max(5, int(timeout_sec))
    if emit:
        emit(f"[langskills] XHS CAPTCHA detected; please complete it in the opened browser (timeout {timeout_sec}s).")
    try:
        page.bring_to_front()
    except Exception:
        pass
    while time.time() < deadline:
        if not _page_needs_verification(page):
            return
        time.sleep(2)
    raise RuntimeError(f"XHS verification not completed within {timeout_sec}s.")


def fetch_xhs_text(
    url: str,
    *,
    timeout_ms: int = 25_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> FetchResult:
    """
    Fetch a Xiaohongshu (XHS) page via Playwright, with optional login (cookie/qrcode/phone).
    """
    u = str(url or "").strip()
    if not u:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="xhs", used_playwright=False)
    if not playwright_available():
        raise RuntimeError("Playwright is not available. Install it and run `playwright install chromium`.")

    headless_override: bool | None = None
    is_headless = _effective_headless(headless_override)

    with playwright_page(platform="xhs", timeout_ms=timeout_ms, headless=headless_override) as page:
        if not ensure_xhs_login(page, return_url=u, emit=emit, info=info, headless=is_headless):
            raise RuntimeError("XHS login failed.")

        if _page_needs_verification(page):
            auth_dir = resolve_auth_dir()
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            shot = auth_dir / f"xhs_verify_{ts}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                if info is not None:
                    info["verification_screenshot"] = shot.as_posix()
            except Exception:
                pass

            timeout_sec = int(_env_int("LANGSKILLS_XHS_VERIFY_TIMEOUT_SEC", 600))
            _wait_for_manual_verification(page, headless=is_headless, timeout_sec=timeout_sec, emit=emit)
            try:
                page.goto(u, wait_until="domcontentloaded")
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        # Some accounts get redirected to a verification page after initial render; re-check after waiting.
        if _page_needs_verification(page):
            auth_dir = resolve_auth_dir()
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            shot = auth_dir / f"xhs_verify_{ts}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                if info is not None:
                    info["verification_screenshot"] = shot.as_posix()
                    info["captcha_detected"] = True
                    info["captcha_url"] = str(getattr(page, "url", "") or "")
            except Exception:
                pass

            timeout_sec = int(_env_int("LANGSKILLS_XHS_VERIFY_TIMEOUT_SEC", 600))
            _wait_for_manual_verification(page, headless=is_headless, timeout_sec=timeout_sec, emit=emit)
            try:
                page.goto(u, wait_until="domcontentloaded")
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
            platform="xhs",
            used_playwright=True,
            debug=debug,
        )
