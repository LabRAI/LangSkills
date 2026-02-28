from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..sources.arxiv import search_arxiv
from ..sources.baidu import search_baidu_urls
from ..sources.github import github_fetch_readme_excerpt_raw, github_search_top_repos
from ..sources.playwright_utils import load_playwright_config, playwright_available, playwright_page
from ..sources.stackoverflow import (
    StackQuestion,
    pick_answer_for_question,
    stack_fetch_answers_with_body,
    stack_fetch_questions_with_body,
    stack_search_top_questions,
)
from ..sources.webpage import fetch_webpage_text
from ..sources.xhs import fetch_xhs_text, search_xhs_urls
from ..sources.zhihu import fetch_zhihu_text, search_zhihu_urls
from ..utils.fs import ensure_dir, write_json_atomic, write_text_atomic
from ..utils.time import utc_now_iso_z


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    status: str
    duration_ms: int
    details: dict[str, Any]
    error: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "error": self.error,
            "suggestion": self.suggestion,
        }


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _classify_error(err: Exception) -> tuple[str, str]:
    msg = str(err or "").strip()
    low = msg.lower()
    if "requires a visible browser" in low or "requires_headful" in low:
        return "needs_auth_headful", msg
    if "playwright is not available" in low:
        return "missing_playwright", msg
    if "executable doesn't exist" in low or "playwright install" in low:
        return "missing_browser", msg
    if "http 429" in low or "rate limit" in low:
        return "rate_limited", msg
    if "captcha" in low or "\u9a8c\u8bc1" in msg:
        return "captcha", msg
    return "error", msg


def _run_check(name: str, fn: Callable[[], dict[str, Any]]) -> CheckResult:
    t0 = time.perf_counter()
    try:
        details = fn() or {}
        ok = bool(details.get("ok", True))
        status = str(details.get("status") or ("ok" if ok else "fail"))
        suggestion = str(details.get("suggestion") or "")
        return CheckResult(
            name=name,
            ok=ok,
            status=status,
            duration_ms=_ms(t0),
            details={k: v for k, v in details.items() if k not in {"ok", "status", "suggestion"}},
            suggestion=suggestion,
        )
    except Exception as e:
        kind, msg = _classify_error(e)
        suggestion = ""
        if kind == "missing_playwright":
            suggestion = "Install Playwright into the venv: `./.venv/bin/python -m pip install playwright`"
        elif kind == "missing_browser":
            suggestion = "Install Playwright browsers: `./.venv/bin/python -m playwright install chromium`"
        elif kind == "needs_auth_headful":
            suggestion = "Run `./.venv/bin/python langskills_cli.py auth <zhihu|xhs>` once with `LANGSKILLS_PLAYWRIGHT_HEADLESS=0`"
        elif kind == "rate_limited":
            suggestion = "Add an API token (e.g. `GITHUB_TOKEN`) and/or reduce concurrency/QPS"
        elif kind == "captcha":
            suggestion = "Complete verification in a headed browser once, then reuse persistent profile/storage_state"
        return CheckResult(
            name=name,
            ok=False,
            status=kind,
            duration_ms=_ms(t0),
            details={},
            error=msg,
            suggestion=suggestion,
        )


def _render_report_md(*, run_id: str, query: str, results: list[CheckResult], out_dir: Path) -> str:
    lines: list[str] = []
    lines.append(f"# Sources Audit Report\n")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- query: `{query}`")
    lines.append(f"- generated_at: `{utc_now_iso_z()}`")
    lines.append(f"- out_dir: `{out_dir.as_posix()}`\n")

    lines.append("## Summary\n")
    for r in results:
        status = r.status
        ok = "PASS" if r.ok else "FAIL"
        lines.append(f"- {ok} `{r.name}` ({status}, {r.duration_ms}ms)")
    lines.append("")

    lines.append("## Details\n")
    for r in results:
        lines.append(f"### {r.name}\n")
        lines.append(f"- ok: `{r.ok}`")
        lines.append(f"- status: `{r.status}`")
        lines.append(f"- duration_ms: `{r.duration_ms}`")
        if r.error:
            lines.append(f"- error: `{r.error}`")
        if r.suggestion:
            lines.append(f"- suggestion: `{r.suggestion}`")
        if r.details:
            lines.append("- details:")
            for k, v in r.details.items():
                lines.append(f"  - `{k}`: `{json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_sources_audit(
    *,
    repo_root: str | Path,
    query: str,
    out_dir: str | Path,
    timeout_ms: int = 25_000,
    limit: int = 5,
    webpage_concurrency: int = 6,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    ensure_dir(out_dir)

    run_id = out_dir.name
    q = str(query or "").strip() or "python"
    lim = max(1, min(50, int(limit or 5)))
    timeout_ms = max(2_000, min(180_000, int(timeout_ms or 25_000)))
    webpage_concurrency = max(1, min(32, int(webpage_concurrency or 6)))

    checks: list[CheckResult] = []

    def check_playwright() -> dict[str, Any]:
        ok = playwright_available()
        details: dict[str, Any] = {"playwright_available": ok}
        if not ok:
            return {"ok": False, "status": "missing_playwright", **details}
        # Smoke a page open/close so we can distinguish "installed" vs "browser missing".
        with playwright_page(platform="audit", timeout_ms=5_000, headless=None) as page:
            page.goto("about:blank", wait_until="domcontentloaded")
        return {"ok": True, "status": "ok", **details}

    checks.append(_run_check("playwright", check_playwright))

    def check_tavily() -> dict[str, Any]:
        has_key = bool(str(os.environ.get("TAVILY_API_KEY") or os.environ.get("TAVILY_TOKEN") or "").strip())
        if not has_key:
            return {
                "ok": True,
                "status": "skipped",
                "suggestion": "Set `TAVILY_API_KEY` (or `TAVILY_TOKEN`) to enable Tavily search",
            }
        t0 = time.perf_counter()
        try:
            from tavily import TavilyClient  # type: ignore
        except Exception as e:
            return {
                "ok": False,
                "status": "missing_dependency",
                "error": f"{type(e).__name__}: {e}",
                "suggestion": "Install `tavily-python` into the venv",
            }

        key = str(os.environ.get("TAVILY_API_KEY") or os.environ.get("TAVILY_TOKEN") or "").strip()
        try:
            client = TavilyClient(api_key=key)
            resp: dict[str, Any] = client.search(q, max_results=min(20, lim), search_depth="advanced")  # type: ignore[arg-type]
            results = resp.get("results") if isinstance(resp, dict) else None
            urls = [str(r.get("url") or "").strip() for r in (results or []) if isinstance(r, dict)]
            urls = [u for u in urls if u]
            return {"ok": bool(urls), "status": "ok" if urls else "empty", "count": len(urls), "duration_ms_inner": _ms(t0)}
        except Exception as e:
            msg = str(e or "").strip()
            low = msg.lower()
            status = "error"
            suggestion = "Check Tavily API key / quota / network"
            if "usage limit" in low or "exceeds your plan" in low:
                status = "quota_exhausted"
                suggestion = "Tavily quota exhausted; upgrade plan or switch providers (e.g. Baidu) for bulk runs"
            return {
                "ok": False,
                "status": status,
                "error": f"{type(e).__name__}: {msg}",
                "suggestion": suggestion,
                "duration_ms_inner": _ms(t0),
            }

    checks.append(_run_check("tavily_search(api)", check_tavily))

    def check_arxiv() -> dict[str, Any]:
        t0 = time.perf_counter()
        items = search_arxiv(q, max_results=lim)
        return {
            "ok": bool(items),
            "status": "ok" if items else "empty",
            "count": len(items),
            "duration_ms_inner": _ms(t0),
        }

    checks.append(_run_check("arxiv_search", check_arxiv))

    def check_github() -> dict[str, Any]:
        t0 = time.perf_counter()
        repos = github_search_top_repos(query=q, per_page=lim, min_stars=10)
        details: dict[str, Any] = {"count": len(repos)}
        if not repos:
            return {"ok": False, "status": "empty", **details}
        top = repos[0]
        readme = ""
        try:
            readme = github_fetch_readme_excerpt_raw(full_name=top.full_name, default_branch=top.default_branch)
        except Exception as e:
            details["readme_error"] = str(e)
            readme = ""
        details["top_repo"] = {"full_name": top.full_name, "url": top.html_url, "stars": top.stargazers_count, "language": top.language}
        details["readme_chars"] = len(readme)
        return {"ok": True, "status": "ok", "duration_ms_inner": _ms(t0), **details}

    checks.append(_run_check("github_search+readme", check_github))

    def check_stackoverflow() -> dict[str, Any]:
        t0 = time.perf_counter()
        qs: list[StackQuestion] = stack_search_top_questions(q=q, tagged=None, pagesize=lim)
        details: dict[str, Any] = {"count": len(qs)}
        if not qs:
            return {"ok": False, "status": "empty", **details}
        ids = [qq.question_id for qq in qs if qq.question_id]
        if not ids:
            return {"ok": False, "status": "empty_ids", **details}
        questions = stack_fetch_questions_with_body(question_ids=ids)
        answers = stack_fetch_answers_with_body(question_ids=ids)
        by_id = {qq.question_id: qq for qq in questions}
        ok_pick = 0
        for q0 in questions[: min(3, len(questions))]:
            a = pick_answer_for_question(q0, answers)
            if a and a.answer_id:
                ok_pick += 1
        details["fetched_questions"] = len(questions)
        details["fetched_answers"] = len(answers)
        details["answer_picks_ok"] = ok_pick
        details["sample_title"] = (qs[0].title or "").strip()
        sample_q = by_id.get(ids[0]) if ids else None
        details["sample_has_body"] = bool(str(getattr(sample_q, "body", "") or "").strip()) if sample_q else False
        return {"ok": True, "status": "ok", "duration_ms_inner": _ms(t0), **details}

    checks.append(_run_check("stackoverflow_search+fetch", check_stackoverflow))

    def check_webpage_bulk() -> dict[str, Any]:
        urls = [
            "https://example.com",
            "https://httpbin.org/html",
            "https://www.python.org/",
            "https://www.rfc-editor.org/rfc/rfc2616",
            "https://docs.python.org/3/",
        ]
        urls = urls[: max(2, min(len(urls), lim))]
        t0 = time.perf_counter()
        ok = 0
        failures: list[str] = []

        def _one(u: str) -> tuple[str, int, int]:
            r = fetch_webpage_text(u, timeout_ms=timeout_ms, retries=1)
            text_len = len(str(r.extracted_text or "").strip())
            return (u, len(str(r.raw_html or "")), text_len)

        with ThreadPoolExecutor(max_workers=webpage_concurrency) as ex:
            futs = {ex.submit(_one, u): u for u in urls}
            samples: list[dict[str, Any]] = []
            for fut in as_completed(futs):
                u = futs[fut]
                try:
                    u0, raw_len, text_len = fut.result()
                    samples.append({"url": u0, "raw_html_chars": raw_len, "extracted_text_chars": text_len})
                    if text_len > 100:
                        ok += 1
                except Exception as e:
                    failures.append(f"{u}: {e}")

        return {
            "ok": ok >= max(1, len(urls) // 2),
            "status": "ok" if ok else "fail",
            "urls": urls,
            "ok_count": ok,
            "failures": failures[:10],
            "samples": samples,
            "duration_ms_inner": _ms(t0),
        }

    checks.append(_run_check("webpage_fetch_bulk(http)", check_webpage_bulk))

    def check_baidu() -> dict[str, Any]:
        t0 = time.perf_counter()
        urls = search_baidu_urls(q, limit=lim, timeout_ms=timeout_ms)
        details: dict[str, Any] = {"count": len(urls), "sample": urls[:3]}
        return {"ok": bool(urls), "status": "ok" if urls else "empty", "duration_ms_inner": _ms(t0), **details}

    checks.append(_run_check("baidu_search(playwright)", check_baidu))

    def check_baidu_fetch_one() -> dict[str, Any]:
        urls = search_baidu_urls(q, limit=3, timeout_ms=timeout_ms)
        if not urls:
            return {"ok": False, "status": "empty"}
        t0 = time.perf_counter()
        u = urls[0]
        r = fetch_webpage_text(u, timeout_ms=timeout_ms, retries=1)
        text_len = len(str(r.extracted_text or "").strip())
        return {
            "ok": text_len > 200,
            "status": "ok" if text_len > 200 else "low_text",
            "url": u,
            "final_url": str(r.final_url or ""),
            "used_playwright": bool(r.used_playwright),
            "extracted_text_chars": text_len,
            "duration_ms_inner": _ms(t0),
        }

    checks.append(_run_check("baidu_url_fetch(sample)", check_baidu_fetch_one))

    def check_zhihu_search() -> dict[str, Any]:
        t0 = time.perf_counter()
        auth: dict[str, Any] = {}
        cfg = load_playwright_config(platform="zhihu", timeout_ms=timeout_ms, headless=None)
        urls = search_zhihu_urls(q, limit=lim, timeout_ms=timeout_ms, info=auth, emit=None)
        details: dict[str, Any] = {
            "count": len(urls),
            "auth": auth,
            "sample": urls[:3],
            "playwright_user_data_dir": str(getattr(cfg, "user_data_dir", "") or ""),
        }
        ok = bool(urls)
        status = "ok" if ok else ("needs_auth" if auth.get("requires_headful") else "empty")
        suggestion = "Run `./.venv/bin/python langskills_cli.py auth zhihu` once (headed) to persist login" if not ok else ""
        return {"ok": ok, "status": status, "suggestion": suggestion, "duration_ms_inner": _ms(t0), **details}

    checks.append(_run_check("zhihu_search(playwright)", check_zhihu_search))

    def check_xhs_search() -> dict[str, Any]:
        t0 = time.perf_counter()
        auth: dict[str, Any] = {}
        cfg = load_playwright_config(platform="xhs", timeout_ms=timeout_ms, headless=None)
        urls = search_xhs_urls(q, limit=lim, timeout_ms=timeout_ms, info=auth, emit=None)
        details: dict[str, Any] = {
            "count": len(urls),
            "auth": auth,
            "sample": urls[:3],
            "playwright_user_data_dir": str(getattr(cfg, "user_data_dir", "") or ""),
        }
        ok = bool(urls)
        if ok:
            status = "ok"
            suggestion = ""
        elif auth.get("captcha_detected"):
            status = "captcha"
            suggestion = (
                "XHS shows verification (CAPTCHA/slider). "
                "Run `LANGSKILLS_PLAYWRIGHT_HEADLESS=0 ./.venv/bin/python langskills_cli.py auth xhs` once and complete it manually."
            )
        else:
            needs_auth = bool(auth.get("requires_headful") or auth.get("login_ui_detected"))
            status = "needs_auth" if needs_auth else "empty"
            suggestion = (
                "Run `./.venv/bin/python langskills_cli.py auth xhs` once (headed) to persist login" if needs_auth else ""
            )
        return {"ok": ok, "status": status, "suggestion": suggestion, "duration_ms_inner": _ms(t0), **details}

    checks.append(_run_check("xhs_search(playwright)", check_xhs_search))

    def check_zhihu_fetch_sample() -> dict[str, Any]:
        # Without a known-good URL + persisted login, treat as best-effort and skip quickly.
        demo_url = str(Path(repo_root / "runs" / "playwright_auth" / "zhihu_sample_url.txt").read_text(encoding="utf-8").strip()) if (repo_root / "runs" / "playwright_auth" / "zhihu_sample_url.txt").exists() else ""
        if not demo_url:
            return {"ok": True, "status": "skipped", "suggestion": "Create `runs/playwright_auth/zhihu_sample_url.txt` to enable fetch sampling."}
        t0 = time.perf_counter()
        auth: dict[str, Any] = {}
        r = fetch_zhihu_text(demo_url, timeout_ms=timeout_ms, info=auth, emit=None)
        text_len = len(str(r.extracted_text or "").strip())
        return {
            "ok": text_len > 200,
            "status": "ok" if text_len > 200 else "low_text",
            "url": demo_url,
            "final_url": str(r.final_url or ""),
            "used_playwright": bool(r.used_playwright),
            "extracted_text_chars": text_len,
            "auth": auth,
            "duration_ms_inner": _ms(t0),
        }

    checks.append(_run_check("zhihu_fetch(sample)", check_zhihu_fetch_sample))

    def check_xhs_fetch_sample() -> dict[str, Any]:
        demo_url = str(Path(repo_root / "runs" / "playwright_auth" / "xhs_sample_url.txt").read_text(encoding="utf-8").strip()) if (repo_root / "runs" / "playwright_auth" / "xhs_sample_url.txt").exists() else ""
        if not demo_url:
            return {"ok": True, "status": "skipped", "suggestion": "Create `runs/playwright_auth/xhs_sample_url.txt` to enable fetch sampling."}
        t0 = time.perf_counter()
        auth: dict[str, Any] = {}
        r = fetch_xhs_text(demo_url, timeout_ms=timeout_ms, info=auth, emit=None)
        text_len = len(str(r.extracted_text or "").strip())
        return {
            "ok": text_len > 200,
            "status": "ok" if text_len > 200 else "low_text",
            "url": demo_url,
            "final_url": str(r.final_url or ""),
            "used_playwright": bool(r.used_playwright),
            "extracted_text_chars": text_len,
            "auth": auth,
            "duration_ms_inner": _ms(t0),
        }

    checks.append(_run_check("xhs_fetch(sample)", check_xhs_fetch_sample))

    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": utc_now_iso_z(),
        "query": q,
        "timeout_ms": timeout_ms,
        "limit": lim,
        "results": [c.to_dict() for c in checks],
    }

    write_json_atomic(out_dir / "sources_audit.json", payload)
    report_md = _render_report_md(run_id=run_id, query=q, results=checks, out_dir=out_dir)
    write_text_atomic(out_dir / "sources_audit.md", report_md)

    return payload
