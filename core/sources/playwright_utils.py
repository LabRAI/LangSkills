from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from ..env import env_bool as _env_bool
from ..utils.paths import repo_root


@contextmanager
def _prefer_installed_playwright() -> Iterator[None]:
    """
    Prefer the PyPI `playwright` package over a repo-local top-level `playwright/` directory.

    If a repo/workspace contains a top-level `playwright/` directory (legacy tools,
    local experiments, etc.), it can shadow the real Playwright package on `sys.path`
    (making `import playwright.sync_api` fail).
    """
    import sys

    root = repo_root().resolve()
    removed: list[str] = []
    for entry in list(sys.path):
        if entry == "":
            removed.append(entry)
            continue
        try:
            if Path(entry).resolve() == root:
                removed.append(entry)
        except Exception:
            continue

    for entry in removed:
        try:
            while entry in sys.path:
                sys.path.remove(entry)
        except Exception:
            pass

    try:
        yield
    finally:
        # Restore the entries to the front to keep local imports working as expected.
        for entry in reversed(removed):
            sys.path.insert(0, entry)


def playwright_available() -> bool:
    try:
        with _prefer_installed_playwright():
            import playwright.sync_api  # type: ignore[import-not-found]  # noqa: F401

        return True
    except Exception:
        return False


def parse_cookie_string(cookie_str: str) -> dict[str, str]:
    cookie_dict: dict[str, str] = {}
    for part in str(cookie_str or "").split(";"):
        s = part.strip()
        if not s or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        cookie_dict[k] = v
    return cookie_dict


def add_cookie_string(
    page: Any,
    cookie_str: str,
    *,
    domain: str,
    allow_keys: Iterable[str] | None = None,
) -> int:
    cookie_dict = parse_cookie_string(cookie_str)
    if not cookie_dict:
        return 0
    allow = {str(k or "").strip() for k in allow_keys} if allow_keys is not None else None
    cookies = []
    for name, value in cookie_dict.items():
        key = str(name or "").strip()
        if not key:
            continue
        if allow is not None and key not in allow:
            continue
        cookies.append({"name": key, "value": str(value), "domain": domain, "path": "/"})
    if not cookies:
        return 0
    page.context.add_cookies(cookies)
    return len(cookies)


def cookies_as_dict(context: Any) -> dict[str, str]:
    try:
        cookies = context.cookies()
    except Exception:
        return {}
    out: dict[str, str] = {}
    if isinstance(cookies, list):
        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            value = str(c.get("value") or "")
            if name:
                out[name] = value
    return out


def resolve_auth_dir() -> Path:
    raw = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_AUTH_DIR") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = repo_root() / p
    else:
        p = repo_root() / "runs" / "playwright_auth"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_storage_state_path(*, platform: str | None) -> Path | None:
    """
    Optional Playwright storage_state path (JSON).

    When set, `playwright_page()` will:
    - best-effort load it (only for non-persistent contexts)
    - best-effort write it back on close (both persistent and non-persistent contexts)

    Env vars (highest priority first):
    - LANGSKILLS_<PLATFORM>_STORAGE_STATE_PATH, e.g. LANGSKILLS_ZHIHU_STORAGE_STATE_PATH
    - LANGSKILLS_PLAYWRIGHT_STORAGE_STATE_PATH
    """
    plat = str(platform or "").strip().lower()
    plat_key = f"LANGSKILLS_{plat.upper()}_STORAGE_STATE_PATH" if plat else ""
    raw = str(os.environ.get(plat_key) or "").strip() if plat_key else ""
    if not raw:
        raw = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_STORAGE_STATE_PATH") or "").strip()
    if not raw:
        return None
    if raw.lower() in {"0", "none", "off", "disable", "disabled"}:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = repo_root() / p
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return p


def _resolve_user_data_dir(platform: str | None) -> str | None:
    raw = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_USER_DATA_DIR") or "").strip()
    if raw.lower() in {"0", "none", "off", "disable", "disabled"}:
        return None
    plat = (platform or "default").strip() or "default"

    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = repo_root() / p
        tpl = p.as_posix()
        resolved = tpl % plat if "%s" in tpl else tpl
    else:
        # Prefer LangSkills-managed persistent profiles under runs/ (these are created by `langskills auth ...`).
        runs_dir = repo_root() / "runs" / "browser_data" / f"{plat}_user_data_dir"
        resolved = runs_dir.as_posix()

    try:
        Path(resolved).mkdir(parents=True, exist_ok=True)
        return resolved
    except Exception:
        return None


@dataclass(frozen=True)
class PlaywrightConfig:
    headless: bool
    timeout_ms: int
    user_data_dir: str | None
    locale: str
    user_agent: str
    extra_http_headers: dict[str, str]
    viewport: dict[str, int] | None


def load_playwright_config(
    *,
    platform: str | None,
    timeout_ms: int | None = None,
    headless: bool | None = None,
) -> PlaywrightConfig:
    default_timeout = 25_000
    raw_timeout = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_TIMEOUT_MS") or "").strip()
    try:
        base_timeout = int(raw_timeout) if raw_timeout else default_timeout
    except Exception:
        base_timeout = default_timeout
    timeout = int(timeout_ms if timeout_ms is not None else base_timeout)
    timeout = max(2_000, min(180_000, timeout))

    if headless is None:
        headless = _env_bool("LANGSKILLS_PLAYWRIGHT_HEADLESS", True)

    user_data_dir = _resolve_user_data_dir(platform)

    locale = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_LOCALE") or "zh-CN").strip() or "zh-CN"
    user_agent = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_USER_AGENT") or "").strip()
    if not user_agent:
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"

    extra_http_headers: dict[str, str] = {}
    accept_lang = str(os.environ.get("LANGSKILLS_PLAYWRIGHT_ACCEPT_LANGUAGE") or "").strip()
    if accept_lang:
        extra_http_headers["Accept-Language"] = accept_lang
    else:
        extra_http_headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"

    viewport: dict[str, int] | None = None
    if _env_bool("LANGSKILLS_PLAYWRIGHT_VIEWPORT", True):
        viewport = {"width": 1280, "height": 720}

    return PlaywrightConfig(
        headless=bool(headless),
        timeout_ms=timeout,
        user_data_dir=user_data_dir,
        locale=locale,
        user_agent=user_agent,
        extra_http_headers=extra_http_headers,
        viewport=viewport,
    )


def wait_until(*, predicate: Callable[[], bool], timeout_sec: int, poll_sec: float = 1.0) -> bool:
    deadline = time.time() + max(1, int(timeout_sec))
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(max(0.1, float(poll_sec)))
    return False


@contextmanager
def playwright_page(
    *, platform: str | None, timeout_ms: int = 25_000, headless: bool | None = None
) -> Iterator[Any]:
    """
    Best-effort Playwright page context.

    This is an optional integration: if Playwright (or browsers) are not installed,
    callers should catch exceptions and fall back to non-browser implementations.
    """
    with _prefer_installed_playwright():
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    cfg = load_playwright_config(platform=platform, timeout_ms=timeout_ms, headless=headless)
    storage_state_path = resolve_storage_state_path(platform=platform)

    with sync_playwright() as p:
        if cfg.user_data_dir:
            context = p.chromium.launch_persistent_context(  # type: ignore[attr-defined]
                user_data_dir=cfg.user_data_dir,
                headless=cfg.headless,
                locale=cfg.locale,
                user_agent=cfg.user_agent,
                viewport=cfg.viewport,
                extra_http_headers=cfg.extra_http_headers,
            )
            page = context.new_page()
            page.set_default_timeout(cfg.timeout_ms)
            try:
                yield page
            finally:
                try:
                    if storage_state_path:
                        context.storage_state(path=str(storage_state_path))
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
        else:
            browser = p.chromium.launch(headless=cfg.headless)  # type: ignore[attr-defined]
            storage_state: str | None = None
            try:
                if storage_state_path and storage_state_path.exists():
                    storage_state = str(storage_state_path)
            except Exception:
                storage_state = None

            context = browser.new_context(
                locale=cfg.locale,
                user_agent=cfg.user_agent,
                viewport=cfg.viewport,
                extra_http_headers=cfg.extra_http_headers,
                storage_state=storage_state,
            )
            page = context.new_page()
            page.set_default_timeout(cfg.timeout_ms)
            try:
                yield page
            finally:
                try:
                    if storage_state_path:
                        context.storage_state(path=str(storage_state_path))
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
