from __future__ import annotations

import html as _html
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from ..utils.http import HttpError, fetch_with_retries, try_parse_json_object
from ..utils.paths import repo_root
from ..utils.text import html_to_text, truncate_text
from .types import FetchResult


@dataclass(frozen=True)
class StackQuestion:
    question_id: int
    title: str
    link: str
    accepted_answer_id: int
    body: str = ""


@dataclass(frozen=True)
class StackAnswer:
    answer_id: int
    question_id: int
    is_accepted: bool
    score: int
    body: str


def _stackexchange_key() -> str:
    return str(
        os.environ.get("STACKEXCHANGE_KEY")
        or os.environ.get("STACKEXCHANGE_API_KEY")
        or os.environ.get("LANGSKILLS_STACKEXCHANGE_KEY")
        or ""
    ).strip()


def _apply_stackexchange_key(params: dict[str, str]) -> None:
    key = _stackexchange_key()
    if key:
        params["key"] = key


def _maybe_backoff(parsed: dict | None) -> None:
    if not isinstance(parsed, dict):
        return
    raw = parsed.get("backoff")
    try:
        backoff = float(raw) if raw is not None else 0.0
    except Exception:
        backoff = 0.0
    if backoff > 0:
        time.sleep(min(max(0.0, backoff), 60.0))


def _stack_rate_lock_path() -> str:
    p = repo_root() / "runs" / "stackexchange_rate.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.as_posix()


def _stack_get_next_allowed_ts() -> float:
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover - non-POSIX platforms
        return 0.0
    path = _stack_rate_lock_path()
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


def _stack_set_next_allowed_ts(next_ts: float) -> None:
    try:
        import fcntl  # type: ignore
    except Exception:  # pragma: no cover - non-POSIX platforms
        return
    path = _stack_rate_lock_path()
    try:
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                f.truncate()
                f.write(str(float(next_ts or 0.0)))
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        return


def _stack_global_backoff(seconds: float) -> None:
    try:
        sec = float(seconds or 0.0)
    except Exception:
        sec = 0.0
    if sec <= 0:
        return
    now = time.time()
    cur = _stack_get_next_allowed_ts()
    _stack_set_next_allowed_ts(max(cur, now + sec))


def _stack_should_skip_request() -> bool:
    next_ts = _stack_get_next_allowed_ts()
    return time.time() < float(next_ts or 0.0)


def _extract_throttle_retry_after_seconds(body_text: str) -> float:
    parsed = try_parse_json_object(body_text)
    if isinstance(parsed, dict):
        raw = parsed.get("backoff")
        try:
            backoff = float(raw) if raw is not None else 0.0
        except Exception:
            backoff = 0.0
        if backoff > 0:
            return min(max(1.0, backoff), 3600.0)
        if str(parsed.get("error_name") or "").strip().lower() == "throttle_violation":
            msg = str(parsed.get("error_message") or "")
            m = re.search(r"(\d+)\s*seconds", msg, flags=re.IGNORECASE)
            if m:
                try:
                    # Some deployments return extremely large retry windows (hours+), which are
                    # not practical for interactive tooling and appear inconsistent across clients.
                    # Keep a conservative cap and rely on retries/looping for long waits.
                    return min(max(1.0, float(int(m.group(1)))), 300.0)
                except Exception:
                    return 60.0
            return 60.0
    return 0.0


def _raise_if_error(parsed: dict | None) -> None:
    if not isinstance(parsed, dict):
        return
    name = str(parsed.get("error_name") or "").strip()
    if not name:
        return
    message = str(parsed.get("error_message") or "").strip()
    error_id = str(parsed.get("error_id") or "").strip()
    detail = f"{name}: {message}".strip(": ")
    if error_id:
        detail = f"{detail} (error_id={error_id})"
    raise RuntimeError(f"StackExchange error: {detail}")


def _curl_fetch_text(url: str, *, timeout_ms: int, accept: str) -> tuple[int, str]:
    timeout_sec = max(1, int(max(1, int(timeout_ms or 20_000)) / 1000))
    marker = "__LANGSKILLS_CURL_HTTP_STATUS__:"
    cmd = [
        "curl",
        "-sS",
        "-L",
        "--max-time",
        str(timeout_sec),
        "-H",
        f"Accept: {accept}",
        "-H",
        "User-Agent: langskills/0.1 (+local)",
        "-w",
        f"\n{marker}%{{http_code}}",
        str(url),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603,S607 - local CLI integration
    out = str(proc.stdout or "")
    if marker not in out:
        raise RuntimeError(f"curl fetch failed: missing status marker (rc={int(proc.returncode)})")
    body, status_raw = out.rsplit(marker, 1)
    try:
        status = int(str(status_raw or "").strip())
    except Exception:
        status = 0
    return status, body


def _stack_fetch_json(url: str, *, timeout_ms: int = 20_000) -> dict | list | None:
    """
    Fetch StackExchange API JSON.

    Note: Some environments are intermittently blocked/throttled by Cloudflare when using Python HTTP clients.
    We fall back to `curl` (when available) because it tends to be more reliable in practice.
    """
    try:
        resp = fetch_with_retries(url, timeout_ms=timeout_ms, retries=2, accept="application/json")
        return try_parse_json_object(resp.text)
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) not in {400, 429}:
            raise
        try:
            status2, body2 = _curl_fetch_text(url, timeout_ms=timeout_ms, accept="application/json")
            if not (200 <= int(status2) <= 299):
                raise HttpError(f"HTTP {status2}: {url}", status=int(status2), body_preview=str(body2 or "")[:2000], headers={})
            return try_parse_json_object(body2)
        except Exception:
            raise
    except Exception:
        status2, body2 = _curl_fetch_text(url, timeout_ms=timeout_ms, accept="application/json")
        if not (200 <= int(status2) <= 299):
            raise HttpError(f"HTTP {status2}: {url}", status=int(status2), body_preview=str(body2 or "")[:2000], headers={})
        return try_parse_json_object(body2)


def stack_search_top_questions(*, q: str, tagged: str | None, pagesize: int = 10, page: int = 1) -> list[StackQuestion]:
    if _stack_should_skip_request():
        return []
    base = "https://api.stackexchange.com/2.3/search/advanced"
    params = {
        "order": "desc",
        "sort": "votes",
        "site": "stackoverflow",
        "page": str(max(1, int(page or 1))),
        "pagesize": str(max(1, min(100, int(pagesize or 10)))),
        "q": str(q or ""),
        "filter": "!9_bDDxJY5",  # includes title, link, question_id, accepted_answer_id
    }
    if tagged:
        params["tagged"] = str(tagged or "")
    _apply_stackexchange_key(params)
    url = f"{base}?{urlencode(params)}"

    try:
        parsed = _stack_fetch_json(url, timeout_ms=20_000)
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) in {400, 429}:
            ra = _extract_throttle_retry_after_seconds(str(getattr(e, "body_preview", "") or ""))
            if ra > 0:
                _stack_global_backoff(ra)
                return []
        raise
    except Exception:
        # Network failures (offline, DNS, transient) shouldn't spam logs from discovery loops.
        _stack_global_backoff(60.0)
        return []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise RuntimeError("StackExchange search: invalid JSON response")
    _raise_if_error(parsed)
    _maybe_backoff(parsed)

    out: list[StackQuestion] = []
    for it in parsed["items"][: int(params["pagesize"])]:
        if not isinstance(it, dict):
            continue
        out.append(
            StackQuestion(
                question_id=int(it.get("question_id") or 0),
                title=str(it.get("title") or ""),
                link=str(it.get("link") or ""),
                accepted_answer_id=int(it.get("accepted_answer_id") or 0),
            )
        )
    return out


def stack_fetch_questions_with_body(*, question_ids: list[int]) -> list[StackQuestion]:
    ids = [int(x) for x in (question_ids or []) if int(x or 0) > 0]
    if not ids:
        return []
    if _stack_should_skip_request():
        raise RuntimeError("StackExchange throttled (backoff active)")
    base = f"https://api.stackexchange.com/2.3/questions/{';'.join(str(i) for i in ids)}"
    params = {
        "order": "desc",
        "sort": "activity",
        "site": "stackoverflow",
        "filter": "withbody",
    }
    _apply_stackexchange_key(params)
    url = f"{base}?{urlencode(params)}"

    try:
        parsed = _stack_fetch_json(url, timeout_ms=20_000)
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) in {400, 429}:
            ra = _extract_throttle_retry_after_seconds(str(getattr(e, "body_preview", "") or ""))
            if ra > 0:
                _stack_global_backoff(ra)
                raise RuntimeError(f"StackExchange throttled (retry_after={int(ra)}s)") from e
        raise
    except Exception as e:
        _stack_global_backoff(60.0)
        raise RuntimeError("StackExchange fetch failed") from e
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise RuntimeError("StackExchange questions: invalid JSON response")
    _raise_if_error(parsed)
    _maybe_backoff(parsed)

    out: list[StackQuestion] = []
    for it in parsed["items"]:
        if not isinstance(it, dict):
            continue
        out.append(
            StackQuestion(
                question_id=int(it.get("question_id") or 0),
                title=str(it.get("title") or ""),
                link=str(it.get("link") or ""),
                accepted_answer_id=int(it.get("accepted_answer_id") or 0),
                body=str(it.get("body") or ""),
            )
        )
    return out


def stack_fetch_answers_with_body(*, question_ids: list[int]) -> list[StackAnswer]:
    ids = [int(x) for x in (question_ids or []) if int(x or 0) > 0]
    if not ids:
        return []
    if _stack_should_skip_request():
        raise RuntimeError("StackExchange throttled (backoff active)")
    base = f"https://api.stackexchange.com/2.3/questions/{';'.join(str(i) for i in ids)}/answers"
    params = {
        "order": "desc",
        "sort": "votes",
        "site": "stackoverflow",
        "pagesize": "50",
        "filter": "withbody",
    }
    _apply_stackexchange_key(params)
    url = f"{base}?{urlencode(params)}"

    try:
        parsed = _stack_fetch_json(url, timeout_ms=20_000)
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) in {400, 429}:
            ra = _extract_throttle_retry_after_seconds(str(getattr(e, "body_preview", "") or ""))
            if ra > 0:
                _stack_global_backoff(ra)
                raise RuntimeError(f"StackExchange throttled (retry_after={int(ra)}s)") from e
        raise
    except Exception as e:
        _stack_global_backoff(60.0)
        raise RuntimeError("StackExchange fetch failed") from e
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise RuntimeError("StackExchange answers: invalid JSON response")
    _raise_if_error(parsed)
    _maybe_backoff(parsed)

    out: list[StackAnswer] = []
    for it in parsed["items"]:
        if not isinstance(it, dict):
            continue
        out.append(
            StackAnswer(
                answer_id=int(it.get("answer_id") or 0),
                question_id=int(it.get("question_id") or 0),
                is_accepted=bool(it.get("is_accepted") or False),
                score=int(it.get("score") or 0),
                body=str(it.get("body") or ""),
            )
        )
    return out


def stack_fetch_answers_by_id_with_body(*, answer_ids: list[int]) -> list[StackAnswer]:
    ids = [int(x) for x in (answer_ids or []) if int(x or 0) > 0]
    if not ids:
        return []
    if _stack_should_skip_request():
        raise RuntimeError("StackExchange throttled (backoff active)")
    base = f"https://api.stackexchange.com/2.3/answers/{';'.join(str(i) for i in ids)}"
    params = {
        "order": "desc",
        "sort": "activity",
        "site": "stackoverflow",
        "filter": "withbody",
    }
    _apply_stackexchange_key(params)
    url = f"{base}?{urlencode(params)}"

    try:
        parsed = _stack_fetch_json(url, timeout_ms=20_000)
    except HttpError as e:
        if int(getattr(e, "status", 0) or 0) in {400, 429}:
            ra = _extract_throttle_retry_after_seconds(str(getattr(e, "body_preview", "") or ""))
            if ra > 0:
                _stack_global_backoff(ra)
                raise RuntimeError(f"StackExchange throttled (retry_after={int(ra)}s)") from e
        raise
    except Exception as e:
        _stack_global_backoff(60.0)
        raise RuntimeError("StackExchange fetch failed") from e
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise RuntimeError("StackExchange answers: invalid JSON response")
    _raise_if_error(parsed)
    _maybe_backoff(parsed)

    out: list[StackAnswer] = []
    for it in parsed["items"]:
        if not isinstance(it, dict):
            continue
        out.append(
            StackAnswer(
                answer_id=int(it.get("answer_id") or 0),
                question_id=int(it.get("question_id") or 0),
                is_accepted=bool(it.get("is_accepted") or False),
                score=int(it.get("score") or 0),
                body=str(it.get("body") or ""),
            )
        )
    return out


def pick_answer_for_question(question: StackQuestion, answers: list[StackAnswer]) -> StackAnswer | None:
    qid = int(question.question_id or 0)
    if not qid:
        return None

    accepted_id = int(question.accepted_answer_id or 0)
    if accepted_id:
        for a in answers:
            if int(a.answer_id or 0) == accepted_id:
                return a

    candidates = [a for a in answers if int(a.question_id or 0) == qid]
    candidates.sort(key=lambda a: ((0 if a.is_accepted else 1), -int(a.score or 0)))
    return candidates[0] if candidates else None


def parse_stackoverflow_question_id(url: str) -> int:
    u = str(url or "")
    m = re.search(r"/questions/(\d+)(?:[/?#]|$)", u, flags=re.IGNORECASE) or re.search(r"/q/(\d+)(?:[/?#]|$)", u, flags=re.IGNORECASE)
    if not m:
        return 0
    try:
        n = int(m.group(1))
        return n if n > 0 else 0
    except Exception:
        return 0


def combine_question_answer_text(question: StackQuestion, answer: StackAnswer | None) -> str:
    q_text = html_to_text(question.body or "")
    a_text = html_to_text(answer.body or "") if answer else ""
    combined = f"QUESTION:\n{question.title}\n\n{q_text}\n\nANSWER:\n{a_text}"
    return truncate_text(combined, 12_000)


_STACKPRINTER_TITLE_RE = re.compile(r"<title>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)


def _extract_html_title(html: str) -> str:
    m = _STACKPRINTER_TITLE_RE.search(str(html or ""))
    if not m:
        return ""
    t = str(m.group(1) or "")
    t = re.sub(r"\s+", " ", t, flags=re.MULTILINE).strip()
    try:
        return str(_html.unescape(t) or "").strip()
    except Exception:
        return t


def fetch_stackprinter_text(question_id: int, *, timeout_ms: int = 20_000) -> FetchResult:
    qid = int(question_id or 0)
    if qid <= 0:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="stackprinter", used_playwright=False)
    url = (
        "https://stackprinter.appspot.com/export"
        f"?question={qid}&service=stackoverflow&language=en&width=640"
        "&printer=false&linktohome=true"
    )
    resp = fetch_with_retries(url, timeout_ms=timeout_ms, retries=2, accept="text/html,*/*")
    title = _extract_html_title(resp.text)
    extracted = html_to_text(resp.text)
    extracted = truncate_text(extracted, 12_000)
    return FetchResult(
        raw_html=resp.text,
        extracted_text=extracted,
        final_url=f"https://stackoverflow.com/questions/{qid}",
        title=title,
        platform="stackprinter",
        used_playwright=False,
    )


def fetch_stackoverflow_text(
    url: str,
    *,
    timeout_ms: int = 20_000,
    info: dict[str, Any] | None = None,
    emit: Callable[[str], None] | None = None,
) -> FetchResult:
    """
    Fetch a StackOverflow question.

    - If `STACKEXCHANGE_KEY` is configured, use the StackExchange API (question + best answer).
    - Otherwise, fall back to fetching the public HTML page (HTTP/Playwright) to avoid quota throttling.
    """
    u = str(url or "").strip()
    if not u:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="stackoverflow", used_playwright=False)

    from .webpage import fetch_webpage_text

    def _fallback_webpage(*, status: str, question_id: int = 0, api_error: Exception | None = None) -> FetchResult:
        if info is not None:
            info["status"] = str(status or "fallback_webpage").strip() or "fallback_webpage"
            info["mode"] = "webpage"
            if int(question_id or 0) > 0:
                info["question_id"] = int(question_id)
            if api_error is not None:
                info["api_error"] = f"{type(api_error).__name__}: {api_error}"

        res = fetch_webpage_text(u, timeout_ms=timeout_ms, retries=2)
        debug = dict(getattr(res, "debug", {}) or {})
        if info is not None:
            debug["forum"] = info
        return FetchResult(
            raw_html=res.raw_html,
            extracted_text=res.extracted_text,
            final_url=str(res.final_url or u),
            title=str(res.title or ""),
            platform="stackoverflow",
            used_playwright=bool(res.used_playwright),
            debug=debug,
        )

    qid = parse_stackoverflow_question_id(u)
    if not qid:
        return _fallback_webpage(status="fallback_webpage_no_qid")

    if not _stackexchange_key():
        if emit:
            emit("[langskills] StackOverflow fetch: no STACKEXCHANGE_KEY; using webpage fallback")
        return _fallback_webpage(status="fallback_webpage_no_key", question_id=qid)

    if emit:
        emit(f"[langskills] StackOverflow fetch: question_id={qid}")

    try:
        qs = stack_fetch_questions_with_body(question_ids=[qid])
        if not qs:
            raise RuntimeError(f"StackOverflow fetch: question not found (id={qid})")
        q = qs[0]
        answers = stack_fetch_answers_with_body(question_ids=[qid])
        a = pick_answer_for_question(q, answers)
    except Exception as e:
        if emit:
            emit(f"[langskills] StackOverflow fetch: API failed; using webpage fallback ({type(e).__name__}: {e})")
        return _fallback_webpage(status="fallback_webpage_api_error", question_id=qid, api_error=e)

    extracted = combine_question_answer_text(q, a)
    raw_html = _html.unescape(q.body or "")
    if a and a.body:
        raw_html = f"{raw_html}\n\n{_html.unescape(a.body)}"

    debug: dict[str, Any] = {}
    if info is not None:
        info["mode"] = "api"
        info["question_id"] = q.question_id
        info["accepted_answer_id"] = q.accepted_answer_id
        info["answer_id"] = int(getattr(a, "answer_id", 0) or 0) if a else 0
        info["answers_fetched"] = len(answers)
        debug["forum"] = info

    return FetchResult(
        raw_html=raw_html,
        extracted_text=extracted,
        final_url=str(q.link or u),
        title=str(q.title or ""),
        platform="stackoverflow",
        used_playwright=False,
        debug=debug,
    )
