from __future__ import annotations

import argparse
import html as _html
import json
import os
import queue as queue_mod
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from ..config import DOMAIN_CONFIG, extract_url_hostname
from ..queue import QueueSettings, QueueStore
from ..sources.github import GithubRepo, github_search_top_repos, github_search_top_repos_traverse, parse_github_full_name_from_url
from ..sources.stackoverflow import StackQuestion, parse_stackoverflow_question_id, stack_search_top_questions
from ..sources.web_search import search_web_urls, search_web_urls_with_tavily
from ..utils.paths import repo_root
from ..utils.http import HttpError, fetch_with_retries


WEB_QUERY_VARIANTS: list[str] = [
    "",
    "tutorial",
    "guide",
    "how to",
    "best practices",
    "troubleshooting",
    "examples",
    "cheatsheet",
    "configuration",
    "commands",
    "chinese",
    "hands-on",
    "faq",
]

GITHUB_QUERY_VARIANTS: list[str] = [
    "",
    "awesome {topic}",
    "library",
    "tooling",
    "cli",
    "sdk",
    "example",
    "template",
    "starter",
    "boilerplate",
    "best practices",
    "tutorial",
    "guide",
]


def _variant_query(topic: str, *, idx: int, round_id: int) -> str:
    suffix = WEB_QUERY_VARIANTS[max(0, int(round_id)) % len(WEB_QUERY_VARIANTS)]
    if not suffix:
        return topic
    if suffix.startswith("how "):
        return f"{suffix} {topic}".strip()
    return f"{topic} {suffix}".strip()


def _github_variant_query(base_query: str, topic: str, *, idx: int, round_id: int) -> str:
    # Keep the same variant for a full GitHub page cycle (1..10), so we can
    # walk deeper pages first instead of changing the query every round.
    block = max(0, int(round_id)) // 10
    suffix = GITHUB_QUERY_VARIANTS[block % len(GITHUB_QUERY_VARIANTS)]
    if not suffix:
        return base_query
    extra = suffix
    if "{topic}" in suffix:
        base_norm = str(base_query or "").lower()
        topic_norm = str(topic or "").strip().lower()
        if topic_norm and topic_norm in base_norm:
            extra = suffix.replace("{topic}", "").strip()
        else:
            extra = suffix.format(topic=topic)
    extra = re.sub(r"\s+", " ", str(extra or "")).strip()
    if not extra:
        return base_query
    return f"{base_query} {extra}".strip()


_GITHUB_TOPIC_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*")
_GITHUB_TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "basics",
    "best",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "practices",
    "the",
    "to",
    "vs",
    "with",
    "without",
}


def _compact_github_topic(topic: str, *, max_terms: int) -> str:
    """
    GitHub repo search is sensitive to long natural-language queries.

    Keep a small set of stable tokens (drop common stopwords) to improve hit-rate.
    """
    raw = str(topic or "").strip()
    if not raw:
        return ""
    max_n = max(2, min(12, int(max_terms or 6)))
    tokens = _GITHUB_TOPIC_TOKEN_RE.findall(raw)
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        tl = t.lower()
        if tl in _GITHUB_TOPIC_STOPWORDS:
            continue
        if tl in seen:
            continue
        seen.add(tl)
        out.append(t)
        if len(out) >= max_n:
            break
    if out:
        return " ".join(out)
    return raw


def _classify_url(url: str) -> tuple[str, str, dict[str, Any]]:
    """
    Return (source_type, normalized_url, extra_patch) based on URL patterns.
    """
    u = str(url or "").strip()
    host = extract_url_hostname(u)
    if host and host.endswith("github.com"):
        repo = parse_github_full_name_from_url(u)
        if repo:
            return "github", f"https://github.com/{repo}", {"repo": repo}
    if host and host.endswith("stackoverflow.com"):
        qid = parse_stackoverflow_question_id(u)
        if qid:
            return "forum", u, {"question_id": int(qid)}
    return "webpage", u, {}


def _state_key(provider: str, payload: dict[str, Any]) -> str:
    data = {"provider": str(provider or "").strip().lower(), **payload}
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_state_index(path: Path) -> dict[str, dict[str, Any]]:
    """
    Load persisted state from JSONL/JSON.

    JSONL format: {"key": "...", "ts": 123, "status": "ok"|"error", "next_retry_ts": 0}
    Legacy JSONL entries without status are treated as "ok".
    """
    if not path.exists():
        return {}
    try:
        if path.suffix.lower() == ".jsonl":
            out: dict[str, dict[str, Any]] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except Exception:
                    continue
                if isinstance(obj, str):
                    out[obj] = {"status": "ok", "next_retry_ts": 0.0}
                    continue
                if not isinstance(obj, dict):
                    continue
                key = str(obj.get("key") or "").strip()
                if not key:
                    continue
                status = str(obj.get("status") or "ok").strip().lower() or "ok"
                try:
                    next_retry_ts = float(obj.get("next_retry_ts") or 0.0)
                except Exception:
                    next_retry_ts = 0.0
                out[key] = {"status": status, "next_retry_ts": next_retry_ts}
            return out
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x): {"status": "ok", "next_retry_ts": 0.0} for x in data if str(x).strip()}
        if isinstance(data, dict):
            raw = data.get("keys") or data.get("seen") or []
            if isinstance(raw, list):
                return {str(x): {"status": "ok", "next_retry_ts": 0.0} for x in raw if str(x).strip()}
    except Exception:
        return {}
    return {}


def _append_state_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_state_keys(path: Path) -> set[str]:
    return set(_load_state_index(path).keys())


def _append_state_key(path: Path, key: str) -> None:
    k = str(key or "").strip()
    if not k:
        return
    _append_state_record(path, {"key": k, "ts": int(time.time())})


def _load_topics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Topics file not found: {path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("topics") if isinstance(data, dict) else data
    from ..utils.yaml_lite import safe_load_yaml_text

    data = safe_load_yaml_text(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("topics") or []
    return data or []


def _domain_from_tags(tags: list[str]) -> str:
    keys = set(DOMAIN_CONFIG.keys())
    for tag in tags:
        t = str(tag or "").strip().lower()
        if t in keys:
            return t
    return ""


def _safe_call(fn: Callable[..., list[str]], *, warn: list[str], label: str, **kwargs: Any) -> list[str]:
    try:
        out = fn(**kwargs)
        return out if isinstance(out, list) else []
    except Exception as e:
        warn.append(f"{label}: {e}")
        return []


def _search_web(query: str, limit: int, warn: list[str]) -> list[str]:
    info: dict[str, object] = {}
    try:
        urls = search_web_urls(query, limit=limit, info=info)  # type: ignore[arg-type]
        return urls if isinstance(urls, list) else []
    except Exception as e:
        warn.append(f"web: {e}")
        return []


def _search_baidu(query: str, limit: int, warn: list[str]) -> list[str]:
    try:
        from ..sources.baidu import search_baidu_urls

        return _safe_call(search_baidu_urls, warn=warn, label="baidu", query=query, limit=limit)
    except Exception as e:
        warn.append(f"baidu: {e}")
        return []


def _search_zhihu(query: str, limit: int, warn: list[str]) -> list[str]:
    try:
        from ..sources.zhihu import search_zhihu_urls

        auth: dict[str, object] = {}
        urls = _safe_call(search_zhihu_urls, warn=warn, label="zhihu", query=query, limit=limit, info=auth, emit=print)  # type: ignore[arg-type]
        return urls
    except Exception as e:
        warn.append(f"zhihu: {e}")
        return []


def _search_xhs(query: str, limit: int, warn: list[str]) -> list[str]:
    try:
        from ..sources.xhs import search_xhs_urls

        auth: dict[str, object] = {}
        urls = _safe_call(search_xhs_urls, warn=warn, label="xhs", query=query, limit=limit, info=auth, emit=print)  # type: ignore[arg-type]
        return urls
    except Exception as e:
        warn.append(f"xhs: {e}")
        return []


def _search_github(
    query: str,
    min_stars: int,
    pushed_after: str,
    limit: int,
    warn: list[str],
    *,
    traverse: bool = False,
    pages_per_bucket: int = 1,
    start_bucket: int = 0,
    start_page: int = 1,
) -> tuple[list[GithubRepo], int, float]:
    def retry_after_seconds(err: HttpError) -> float:
        headers = getattr(err, "headers", {}) or {}
        raw_ra = str(headers.get("Retry-After") or headers.get("retry-after") or "").strip()
        try:
            if raw_ra:
                return max(1.0, float(int(raw_ra)))
        except Exception:
            pass
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
        body = str(getattr(err, "body_preview", "") or "").lower()
        if "secondary rate limit" in body or "abuse detection" in body:
            return 60.0
        return 15.0

    try:
        if traverse:
            items = github_search_top_repos_traverse(
                query=query,
                per_page=min(100, max(1, int(limit or 10))),
                pages_per_bucket=max(1, int(pages_per_bucket or 1)),
                max_results=max(1, int(limit or 10)),
                min_stars=min_stars,
                pushed_after=pushed_after or None,
                start_bucket=int(start_bucket or 0),
                start_page=int(start_page or 1),
            )
        else:
            page_n = max(1, min(10, int(start_page or 1)))
            items = github_search_top_repos(
                query=query,
                per_page=limit,
                min_stars=min_stars,
                pushed_after=pushed_after or None,
                page=page_n,
            )
        return items, 0, 0.0
    except HttpError as e:
        ra = retry_after_seconds(e)
        warn.append(f"github: HTTP {e.status}: {e} (retry_after={int(ra)}s)")
        return [], int(e.status or 0), ra
    except Exception as e:
        warn.append(f"github: {e}")
        return [], 0, 0.0


def _search_forum(query: str, tagged: str, limit: int, warn: list[str], *, page: int = 1) -> list[StackQuestion]:
    return _search_forum_mode(
        query,
        tagged,
        limit,
        warn,
        page=page,
        search_mode="auto",
        site_filter="site:stackoverflow.com/questions",
        tavily_depth="basic",
    )


def _has_stackexchange_key_env() -> bool:
    for key in ("STACKEXCHANGE_KEY", "STACKEXCHANGE_API_KEY", "LANGSKILLS_STACKEXCHANGE_KEY"):
        if str(os.environ.get(key) or "").strip():
            return True
    return False


def _stackexchange_backoff_seconds() -> float:
    try:
        path = repo_root() / "runs" / "stackexchange_rate.lock"
    except Exception:
        return 0.0
    try:
        next_ts = float(str(path.read_text(encoding="utf-8") or "").strip() or 0.0)
    except Exception:
        next_ts = 0.0
    return max(0.0, next_ts - time.time()) if next_ts > 0 else 0.0


def _resolve_forum_search_mode(mode: str) -> str:
    m = str(mode or "auto").strip().lower()
    if m not in {"auto", "stackexchange", "tavily", "html"}:
        m = "auto"
    if m == "auto":
        # Prefer StackExchange API search, but fall back to HTML scraping when the API
        # is in a global backoff window (or when a keyless environment is heavily throttled).
        return "html" if _stackexchange_backoff_seconds() > 0 else "stackexchange"
    return m


_STACKOVERFLOW_SEARCH_ITEM_RE = re.compile(
    r'<a[^>]+href="/questions/(?P<qid>\d+)(?:/[^"]*)?"[^>]*class="[^"]*(?:s-link|question-hyperlink)[^"]*"[^>]*>(?P<title>.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)


def _strip_html_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", str(s or ""))


def _search_forum_mode(
    query: str,
    tagged: str,
    limit: int,
    warn: list[str],
    *,
    page: int = 1,
    search_mode: str,
    site_filter: str,
    tavily_depth: str,
) -> list[StackQuestion]:
    mode = _resolve_forum_search_mode(search_mode)
    if mode == "html":
        q = str(query or "").strip()
        tag_raw = str(tagged or "").strip()
        if tag_raw:
            tags = [t for t in re.split(r"[;,\s]+", tag_raw) if t]
            tag_prefix = " ".join(f"[{t}]" for t in tags)
            q = f"{tag_prefix} {q}".strip()
        params = {"q": q, "page": str(max(1, int(page or 1))), "tab": "Votes"}
        url = f"https://stackoverflow.com/search?{urlencode(params)}"
        try:
            resp = fetch_with_retries(url, timeout_ms=20_000, retries=2, accept="text/html,*/*")
        except Exception as e:
            warn.append(f"forum(html): {e}")
            return []

        out: list[StackQuestion] = []
        seen_qids: set[int] = set()
        for m in _STACKOVERFLOW_SEARCH_ITEM_RE.finditer(str(resp.text or "")):
            qid = int(m.group("qid") or 0)
            if qid <= 0 or qid in seen_qids:
                continue
            seen_qids.add(qid)
            title_raw = _strip_html_tags(m.group("title") or "")
            title = re.sub(r"\s+", " ", _html.unescape(title_raw)).strip()
            out.append(
                StackQuestion(
                    question_id=qid,
                    title=title,
                    link=f"https://stackoverflow.com/questions/{qid}",
                    accepted_answer_id=0,
                )
            )
            if len(out) >= max(1, int(limit or 10)):
                break
        return out
    if mode == "tavily":
        depth = str(tavily_depth or "basic").strip().lower()
        if depth not in {"basic", "advanced"}:
            depth = "basic"
        filt = str(site_filter or "").strip()
        if not filt:
            filt = "site:stackoverflow.com/questions"
        tavily_query = " ".join([filt, str(query or "").strip(), str(tagged or "").strip()]).strip()
        try:
            urls = search_web_urls_with_tavily(tavily_query, limit=max(1, int(limit or 10) * 3), search_depth=depth)
        except Exception as e:
            warn.append(f"forum(tavily): {e}")
            return []

        out: list[StackQuestion] = []
        seen_qids: set[int] = set()
        for u in urls:
            qid = int(parse_stackoverflow_question_id(u) or 0)
            if qid <= 0 or qid in seen_qids:
                continue
            seen_qids.add(qid)
            out.append(
                StackQuestion(
                    question_id=qid,
                    title=f"stackoverflow:{qid}",
                    link=f"https://stackoverflow.com/questions/{qid}",
                    accepted_answer_id=0,
                )
            )
            if len(out) >= max(1, int(limit or 10)):
                break
        return out

    try:
        return stack_search_top_questions(q=query, tagged=tagged or None, pagesize=limit, page=page)
    except Exception as e:
        warn.append(f"forum(stackexchange): {e}")
        return []


def cli_queue_seed(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-seed")
    parser.add_argument("--topics-file", default="topics/topics.yaml")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of topics (0 = all)")
    parser.add_argument("--target", type=int, default=50_000, help="Target number of queued sources")
    parser.add_argument("--per-topic", type=int, default=50, help="Results per provider per topic")
    parser.add_argument("--providers", default="web,github,forum,baidu,xhs")
    parser.add_argument(
        "--github-query-mode",
        choices=["topic", "domain_topic"],
        default="topic",
        help="GitHub query construction: 'topic' uses topic keywords; 'domain_topic' prefixes config domain query.",
    )
    parser.add_argument(
        "--github-min-stars",
        type=int,
        default=None,
        help="Override GitHub stars threshold (default: topic mode=10; domain_topic mode=domain config).",
    )
    parser.add_argument("--github-topic-max-terms", type=int, default=6, help="Max keyword terms used in topic mode")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for provider fetches")
    parser.add_argument(
        "--provider-qps",
        default="",
        help="Per-provider rate limit in QPS, e.g. 'web=2,github=0.1,forum=1,baidu=0.2,xhs=0.05'",
    )
    parser.add_argument(
        "--provider-concurrency",
        default="",
        help="Per-provider concurrency, e.g. 'web=2,github=1,forum=2,baidu=1,xhs=1'",
    )
    parser.add_argument(
        "--github-traverse",
        action="store_true",
        help="Use star-bucket traversal + pagination for GitHub search",
    )
    parser.add_argument("--github-pages-per-bucket", type=int, default=1)
    parser.add_argument(
        "--forum-search-mode",
        choices=["auto", "stackexchange", "tavily", "html"],
        default="auto",
        help="Forum search: auto prefers StackExchange API search; falls back to StackOverflow HTML scraping when backoff is active.",
    )
    parser.add_argument(
        "--forum-site-filter",
        default="site:stackoverflow.com/questions",
        help="Tavily-only: extra query filter (recommended to keep it on StackOverflow questions).",
    )
    parser.add_argument(
        "--forum-tavily-depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Tavily-only: search_depth (basic uses less quota).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Repeat provider/topic rounds until target is reached",
    )
    parser.add_argument("--loop-stall-limit", type=int, default=3)
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--stage", default="ingest")
    parser.add_argument(
        "--state-file",
        default="runs/queue_seed_state.jsonl",
        help="Persisted search state (provider/query/page/bucket). Empty to disable.",
    )
    parser.add_argument("--drain-after", action="store_true", help="Enable drain mode after seeding completes")
    parser.add_argument("--no-drain", action="store_true", help="Do not enable drain after seeding")
    parser.add_argument(
        "--progress-every-sec",
        type=int,
        default=60,
        help="Emit progress JSON every N seconds (0 to disable)",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    topics_path = Path(args.topics_file)
    if not topics_path.is_absolute():
        topics_path = root / topics_path
    topics = _load_topics(topics_path)
    if not isinstance(topics, list):
        raise RuntimeError("Invalid topics file format")

    n_limit = int(args.limit or 0)
    picked = topics[:n_limit] if n_limit > 0 else topics

    settings = QueueSettings.from_env(repo_root_path=root)
    if args.queue:
        settings.path = Path(args.queue)
    if not settings.path.is_absolute():
        settings.path = (root / settings.path).resolve()
    queue = QueueStore(settings.path)
    queue.init_db()

    state_path = Path(str(args.state_file or "").strip()) if str(args.state_file or "").strip() else Path()
    if state_path and not state_path.is_absolute():
        state_path = (root / state_path).resolve()
    state_lock = threading.Lock()
    state_index: dict[str, dict[str, Any]] = {}
    if state_path and state_path.name:
        state_index = _load_state_index(state_path)

    target = max(1, int(args.target or 1))
    per_topic = max(1, int(args.per_topic or 1))
    providers = [p.strip().lower() for p in str(args.providers or "").split(",") if p.strip()]
    workers = max(1, int(args.workers or 1))
    forum_search_mode = str(args.forum_search_mode or "auto").strip().lower()
    forum_site_filter = str(args.forum_site_filter or "").strip()
    forum_tavily_depth = str(args.forum_tavily_depth or "basic").strip().lower()

    def _parse_kv_float(raw: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for chunk in str(raw or "").split(","):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, val = part.split("=", 1)
            key = key.strip().lower()
            try:
                out[key] = float(val)
            except Exception:
                continue
        return out

    def _parse_kv_int(raw: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for chunk in str(raw or "").split(","):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, val = part.split("=", 1)
            key = key.strip().lower()
            try:
                out[key] = int(val)
            except Exception:
                continue
        return out

    qps_map = _parse_kv_float(args.provider_qps)
    conc_map = _parse_kv_int(args.provider_concurrency)
    default_conc = {"web": 2, "github": 1, "forum": 2, "baidu": 1, "zhihu": 1, "xhs": 1}
    semaphores: dict[str, threading.Semaphore] = {}
    for p in providers:
        semaphores[p] = threading.Semaphore(int(conc_map.get(p, default_conc.get(p, 1))))
    rate_delay: dict[str, float] = {}
    for p in providers:
        qps = float(qps_map.get(p, 0.0))
        if qps > 0:
            rate_delay[p] = max(0.01, 1.0 / qps)
        else:
            rate_delay[p] = 0.0
    penalty_delay: dict[str, float] = {p: 0.0 for p in providers}
    rate_lock = threading.Lock()
    next_allowed: dict[str, float] = {p: 0.0 for p in providers}

    stats = queue.stats()
    existing = int(stats.get("total") or 0)
    if existing >= target:
        if not args.no_drain:
            queue.set_meta("drain", "1")
        print(json.dumps({"status": "ok", "existing": existing, "target": target, "drain": queue.is_draining()}, ensure_ascii=False, indent=2))
        return 0

    total_new = 0
    warnings: list[str] = []
    topic_entries: list[dict[str, Any]] = []
    for entry in picked:
        if isinstance(entry, dict):
            topic = str(entry.get("topic") or "").strip()
            tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
        else:
            topic = str(entry).strip()
            tags = []
        if not topic:
            continue

        domain = _domain_from_tags([str(t) for t in tags]) if tags else ""
        cfg = DOMAIN_CONFIG.get(domain) if domain and domain in DOMAIN_CONFIG else {}
        gh_cfg = cfg.get("github") if isinstance(cfg.get("github"), dict) else {}
        forum_cfg = cfg.get("forum") if isinstance(cfg.get("forum"), dict) else {}

        gh_query_base_cfg = str(gh_cfg.get("query") or "").strip()
        min_stars_cfg = int(gh_cfg.get("min_stars") or 0)
        pushed_after = str(gh_cfg.get("pushed_after") or "").strip()
        github_query_mode = str(args.github_query_mode or "topic").strip().lower()
        if github_query_mode not in {"topic", "domain_topic"}:
            github_query_mode = "topic"

        if args.github_min_stars is not None:
            min_stars = max(0, int(args.github_min_stars))
        else:
            min_stars = 10 if github_query_mode == "topic" else max(0, int(min_stars_cfg or 0))

        gh_query_base = gh_query_base_cfg if github_query_mode == "domain_topic" else ""
        topic_query = _compact_github_topic(topic, max_terms=int(args.github_topic_max_terms or 6))
        if args.github_traverse:
            gh_query = f"{gh_query_base} {topic_query}".strip() if gh_query_base else topic_query
        else:
            gh_query = (
                f"{gh_query_base} {topic_query} stars:>{min_stars}".strip()
                if gh_query_base
                else f"{topic_query} stars:>{min_stars}".strip()
            )
            if pushed_after:
                gh_query = f"{gh_query} pushed:>{pushed_after}".strip()

        forum_tagged = str(forum_cfg.get("tagged") or "").strip()
        forum_query = " ".join([topic, str(forum_cfg.get("query") or "").strip()]).strip()

        topic_entries.append(
            {
                "idx": len(topic_entries),
                "topic": topic,
                "topic_query": topic_query,
                "tags": tags,
                "domain": domain,
                "gh_query": gh_query or topic,
                "min_stars": min_stars,
                "pushed_after": pushed_after,
                "forum_tagged": forum_tagged,
                "forum_query": forum_query or topic,
            }
        )

    if not topic_entries:
        print(json.dumps({"status": "ok", "queued_new": 0, "existing": existing, "target": target, "total": existing, "drain": queue.is_draining(), "warnings": ["no topics"]}, ensure_ascii=False, indent=2))
        return 0

    n_topics = len(topic_entries)
    counter_lock = threading.Lock()
    progress_every = max(0, int(args.progress_every_sec or 0))
    progress_stop = threading.Event()

    def _build_pairs() -> list[tuple[dict[str, Any], str]]:
        out: list[tuple[dict[str, Any], str]] = []
        for round_idx in range(n_topics):
            for p_idx, provider in enumerate(providers):
                out.append((topic_entries[(round_idx + p_idx) % n_topics], provider))
        return out

    def _capacity_left() -> bool:
        with counter_lock:
            return existing + total_new < target

    def _rate_wait(provider: str) -> None:
        delay = float(rate_delay.get(provider, 0.0))
        penalty = float(penalty_delay.get(provider, 0.0))
        delay = max(delay, penalty)
        if delay <= 0:
            return
        while True:
            with rate_lock:
                now = time.time()
                next_ts = float(next_allowed.get(provider, 0.0))
                if now >= next_ts:
                    next_allowed[provider] = now + delay
                    return
                sleep_for = max(0.01, next_ts - now)
            time.sleep(sleep_for)

    def _bump_penalty(provider: str, *, status: int, retry_after_sec: float = 0.0) -> None:
        if provider not in penalty_delay:
            return
        if int(status) not in {403, 429}:
            return
        with rate_lock:
            base = max(0.1, float(rate_delay.get(provider, 0.1)))
            cur = float(penalty_delay.get(provider, 0.0))
            # exponential backoff, with an optional Retry-After floor (GitHub search limits can be >60s)
            nxt = max(base, cur if cur > 0 else base) * 2.0
            penalty = min(3600.0, max(1.0, nxt))
            try:
                ra = float(retry_after_sec or 0.0)
            except Exception:
                ra = 0.0
            if ra > 0:
                penalty = max(penalty, min(3600.0, ra))
            penalty_delay[provider] = penalty
            next_allowed[provider] = max(next_allowed.get(provider, 0.0), time.time() + penalty_delay[provider])

    def _decay_penalty(provider: str) -> None:
        if provider not in penalty_delay:
            return
        with rate_lock:
            cur = float(penalty_delay.get(provider, 0.0))
            if cur <= 0:
                return
            # decay by 20% on success
            penalty_delay[provider] = max(0.0, cur * 0.8)

    inflight_ttl_sec = 600.0
    try:
        inflight_ttl_sec = max(30.0, float(os.environ.get("LANGSKILLS_QUEUE_SEED_INFLIGHT_TTL_SEC") or 600.0))
    except Exception:
        inflight_ttl_sec = 600.0

    def _state_skip_or_reserve(key: str) -> bool:
        if not (state_path and state_path.name):
            return False
        now = time.time()
        with state_lock:
            rec = state_index.get(key) if isinstance(state_index.get(key), dict) else {}
            status = str(rec.get("status") or "").strip().lower()
            try:
                next_retry_ts = float(rec.get("next_retry_ts") or 0.0)
            except Exception:
                next_retry_ts = 0.0
            if status == "ok":
                return True
            if next_retry_ts > 0 and now < next_retry_ts:
                return True
            next_ts = now + inflight_ttl_sec
            state_index[key] = {"status": "inflight", "next_retry_ts": next_ts}
            _append_state_record(state_path, {"key": key, "ts": int(now), "status": "inflight", "next_retry_ts": next_ts})
            return False

    def _state_mark_ok(key: str) -> None:
        if not (state_path and state_path.name):
            return
        now = time.time()
        with state_lock:
            state_index[key] = {"status": "ok", "next_retry_ts": 0.0}
            _append_state_record(state_path, {"key": key, "ts": int(now), "status": "ok", "next_retry_ts": 0.0})

    def _state_mark_error(key: str, *, retry_after_sec: float) -> None:
        if not (state_path and state_path.name):
            return
        now = time.time()
        try:
            ra = float(retry_after_sec or 0.0)
        except Exception:
            ra = 0.0
        next_ts = now + (ra if ra > 0 else 60.0)
        with state_lock:
            state_index[key] = {"status": "error", "next_retry_ts": next_ts}
            _append_state_record(state_path, {"key": key, "ts": int(now), "status": "error", "next_retry_ts": next_ts})

    rounds = 0
    stall_limit = max(1, int(args.loop_stall_limit or 3))
    stall_rounds = 0
    start_ts = time.time()

    def _progress_worker() -> None:
        while not progress_stop.wait(progress_every):
            try:
                stats = queue.stats()
                total_now = int(stats.get("total") or 0)
                queued_new = max(0, total_now - existing)
                payload = {
                    "progress": {
                        "total": total_now,
                        "queued_new": queued_new,
                        "existing": existing,
                        "target": target,
                        "round": rounds,
                        "elapsed_sec": int(time.time() - start_ts),
                    },
                    "by_source_type": stats.get("by_source_type", {}),
                    "by_status": stats.get("by_status", {}),
                }
                print(json.dumps(payload, ensure_ascii=False), flush=True)
            except Exception:
                # Best effort only; do not interrupt seeding.
                continue

    progress_thread = None
    if progress_every > 0:
        progress_thread = threading.Thread(target=_progress_worker, name="queue-seed-progress", daemon=True)
        progress_thread.start()

    while True:
        if existing + total_new >= target:
            break

        total_before = total_new
        pairs = _build_pairs()
        task_queue: "queue_mod.Queue[tuple[dict[str, Any], str, int]]" = queue_mod.Queue()
        for entry, provider in pairs:
            task_queue.put((entry, provider, rounds))

        stop_event = threading.Event()

        def _worker() -> None:
            nonlocal total_new
            while not stop_event.is_set():
                try:
                    entry, provider, round_id = task_queue.get_nowait()
                except queue_mod.Empty:
                    break
                try:
                    if not _capacity_left():
                        stop_event.set()
                        break
                    sem = semaphores.get(provider)
                    if sem is None:
                        continue
                    with sem:
                        if not _capacity_left():
                            stop_event.set()
                            break

                        topic = str(entry.get("topic") or "").strip()
                        topic_idx = int(entry.get("idx") or 0)
                        tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
                        domain = str(entry.get("domain") or "")
                        gh_query = str(entry.get("gh_query") or topic).strip()
                        min_stars = int(entry.get("min_stars") or 0)
                        pushed_after = str(entry.get("pushed_after") or "").strip()
                        forum_tagged = str(entry.get("forum_tagged") or "").strip()
                        forum_query = str(entry.get("forum_query") or topic).strip()

                        per_provider = min(per_topic, max(1, target - (existing + total_new)))

                        tags_out = [str(t) for t in tags]
                        if provider in {"web", "baidu", "zhihu", "xhs"}:
                            q = _variant_query(topic, idx=topic_idx, round_id=round_id) if provider in {"web", "xhs"} else topic
                            state_key = _state_key(provider, {"query": q})
                            if _state_skip_or_reserve(state_key):
                                continue
                            _rate_wait(provider)
                            if provider == "web":
                                urls = _search_web(q, per_provider, warnings)
                            elif provider == "baidu":
                                urls = _search_baidu(q, per_provider, warnings)
                            elif provider == "zhihu":
                                urls = _search_zhihu(q, per_provider, warnings)
                            else:  # xhs
                                urls = _search_xhs(q, per_provider, warnings)

                            for url in urls:
                                stype, norm_url, extra_patch = _classify_url(url)
                                source_title = str(extra_patch.get("repo") or "") if stype == "github" else ""
                                with counter_lock:
                                    if existing + total_new >= target:
                                        stop_event.set()
                                        break
                                    res = queue.enqueue(
                                        source_id="",
                                        source_type=stype,
                                        source_url=norm_url,
                                        source_title=source_title,
                                        stage=str(args.stage or "ingest"),
                                        priority=0,
                                        max_attempts=settings.max_attempts,
                                        domain=domain,
                                        tags=tags_out,
                                        config_snapshot={"topic": topic, "provider": provider, "round": round_id, "query": q},
                                        extra={"topic": topic, "provider": provider, "tags": tags_out, "round": round_id, "query": q, **extra_patch},
                                    )
                                    if res.get("enqueued"):
                                        total_new += 1
                                if stop_event.is_set():
                                    break
                            _state_mark_ok(state_key)
                        elif provider == "github":
                            # Rotate traversal start to avoid always hitting the same pages/buckets.
                            start_page = 1 + (int(round_id) % 10)
                            start_bucket = int(topic_idx) + int(round_id)
                            topic_query = str(entry.get("topic_query") or topic).strip() or topic
                            gh_query_variant = _github_variant_query(gh_query, topic_query, idx=topic_idx, round_id=round_id)
                            state_key = _state_key(
                                provider,
                                {
                                    "query": gh_query_variant,
                                    "start_bucket": int(start_bucket),
                                    "start_page": int(start_page),
                                    "pages_per_bucket": int(args.github_pages_per_bucket or 1),
                                },
                            )
                            if _state_skip_or_reserve(state_key):
                                continue
                            _rate_wait(provider)
                            repos, gh_status, gh_retry_after = _search_github(
                                gh_query_variant,
                                min_stars,
                                pushed_after,
                                per_provider,
                                warnings,
                                traverse=bool(args.github_traverse),
                                pages_per_bucket=int(args.github_pages_per_bucket or 1),
                                start_bucket=start_bucket,
                                start_page=start_page,
                            )
                            if gh_status:
                                _bump_penalty("github", status=gh_status, retry_after_sec=gh_retry_after)
                                _state_mark_error(state_key, retry_after_sec=gh_retry_after)
                            elif repos:
                                _decay_penalty("github")
                                _state_mark_ok(state_key)
                            else:
                                _state_mark_ok(state_key)
                            for r in repos:
                                url = str(r.html_url or "").strip()
                                if not url:
                                    continue
                                extra_repo = {
                                    "repo": r.full_name,
                                    "description": r.description,
                                    "default_branch": r.default_branch,
                                    "stars": int(r.stargazers_count or 0),
                                    "language": r.language,
                                    "license_spdx": r.license_spdx,
                                    "pushed_at": r.pushed_at,
                                }
                                with counter_lock:
                                    if existing + total_new >= target:
                                        stop_event.set()
                                        break
                                    res = queue.enqueue(
                                        source_id="",
                                        source_type="github",
                                        source_url=url,
                                        source_title=str(r.full_name or ""),
                                        stage=str(args.stage or "ingest"),
                                        priority=0,
                                        max_attempts=settings.max_attempts,
                                        domain=domain,
                                        tags=tags_out,
                                        config_snapshot={
                                            "topic": topic,
                                            "provider": provider,
                                            "round": round_id,
                                            "query": gh_query_variant,
                                            "start_bucket": start_bucket,
                                            "start_page": start_page,
                                        },
                                        extra={
                                            "topic": topic,
                                            "provider": provider,
                                            "tags": tags_out,
                                            "round": round_id,
                                            "query": gh_query_variant,
                                            **extra_repo,
                                        },
                                    )
                                    if res.get("enqueued"):
                                        total_new += 1
                                if stop_event.is_set():
                                    break
                        elif provider == "forum":
                            effective_mode = _resolve_forum_search_mode(forum_search_mode)
                            # StackExchange search is sensitive to long natural-language queries; the
                            # domain-level suffix can make results too sparse and increases duplicates.
                            # Prefer the raw topic for StackExchange, and keep richer variants for other modes.
                            forum_query_use = topic if effective_mode == "stackexchange" else forum_query
                            if effective_mode == "tavily":
                                forum_query_use = _variant_query(forum_query, idx=topic_idx, round_id=round_id)
                            page = 1 + max(0, int(round_id))
                            state_key = _state_key(
                                provider,
                                {
                                    "mode": effective_mode,
                                    "query": forum_query_use,
                                    "tagged": forum_tagged,
                                    "page": int(page),
                                    "site_filter": forum_site_filter if effective_mode == "tavily" else "",
                                    "tavily_depth": forum_tavily_depth if effective_mode == "tavily" else "",
                                },
                            )
                            if _state_skip_or_reserve(state_key):
                                continue
                            _rate_wait(provider)
                            qs = _search_forum_mode(
                                forum_query_use,
                                forum_tagged,
                                per_provider,
                                warnings,
                                page=page,
                                search_mode=effective_mode,
                                site_filter=forum_site_filter,
                                tavily_depth=forum_tavily_depth,
                            )
                            for qobj in qs:
                                url = str(qobj.link or "").strip()
                                if not url:
                                    continue
                                extra_q = {"question_id": int(qobj.question_id or 0), "accepted_answer_id": int(qobj.accepted_answer_id or 0)}
                                if int(extra_q["question_id"] or 0) <= 0:
                                    continue
                                with counter_lock:
                                    if existing + total_new >= target:
                                        stop_event.set()
                                        break
                                    res = queue.enqueue(
                                        source_id="",
                                        source_type="forum",
                                        source_url=url,
                                        source_title=str(qobj.title or ""),
                                        stage=str(args.stage or "ingest"),
                                        priority=0,
                                        max_attempts=settings.max_attempts,
                                        domain=domain,
                                        tags=tags_out,
                                        config_snapshot={
                                            "topic": topic,
                                            "provider": provider,
                                            "round": round_id,
                                            "query": forum_query_use,
                                            "page": page,
                                            "forum_search_mode": effective_mode,
                                            "forum_site_filter": forum_site_filter if effective_mode == "tavily" else "",
                                            "forum_tavily_depth": forum_tavily_depth if effective_mode == "tavily" else "",
                                        },
                                        extra={
                                            "topic": topic,
                                            "provider": provider,
                                            "tags": tags_out,
                                            "round": round_id,
                                            "query": forum_query_use,
                                            "page": page,
                                            "forum_search_mode": effective_mode,
                                            "forum_site_filter": forum_site_filter if effective_mode == "tavily" else "",
                                            "forum_tavily_depth": forum_tavily_depth if effective_mode == "tavily" else "",
                                            **extra_q,
                                        },
                                    )
                                    if res.get("enqueued"):
                                        total_new += 1
                                if stop_event.is_set():
                                    break
                            _state_mark_ok(state_key)
                        else:
                            continue
                finally:
                    task_queue.task_done()

        threads = [threading.Thread(target=_worker, name=f"queue-seed-{rounds}-{i}") for i in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        rounds += 1
        new_in_round = total_new - total_before
        if existing + total_new >= target:
            break
        if not args.loop:
            break
        if new_in_round <= 0:
            stall_rounds += 1
            if stall_rounds >= stall_limit:
                warnings.append("loop_stalled")
                break
        else:
            stall_rounds = 0
        if rounds >= 2000:
            warnings.append("loop_round_limit_reached")
            break

    total = existing + total_new
    if total >= target:
        if not args.no_drain:
            queue.set_meta("drain", "1")
    elif args.drain_after:
        queue.set_meta("drain", "1")

    if progress_thread is not None:
        progress_stop.set()
        try:
            progress_thread.join(timeout=1.0)
        except Exception:
            pass

    print(
        json.dumps(
            {
                "status": "ok",
                "queued_new": total_new,
                "existing": existing,
                "target": target,
                "total": total,
                "drain": queue.is_draining(),
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_queue_seed())
