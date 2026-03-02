from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-posix platforms
    fcntl = None

from ..config import (
    DOMAIN_CONFIG,
    canonicalize_source_url,
    default_domain_for_topic,
    get_crawl_policy_from_config,
    is_url_allowed_by_host_policy,
    license_decision,
    read_license_policy,
)
from ..env import load_dotenv
from ..llm.factory import create_llm_from_env
from ..queue import QueueSettings, QueueStore
from ..repo_understanding.github_remote import GitHubRateLimitError, fetch_repo_tree, is_probably_binary_path
from ..repo_understanding.ingest import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXCLUDE_FILES, classify_tags, detect_language
from ..sources.artifacts import write_source_artifact
from ..sources.github import (
    GithubRepo,
    combine_repo_text,
    github_fetch_blob_raw_text,
    github_fetch_readme_excerpt_raw,
    github_search_top_repos,
    parse_github_blob_url,
    parse_github_full_name_from_url,
)
from ..sources.stackoverflow import (
    combine_question_answer_text,
    fetch_stackprinter_text,
    pick_answer_for_question,
    stack_fetch_answers_by_id_with_body,
    stack_fetch_answers_with_body,
    stack_fetch_questions_with_body,
    stack_search_top_questions,
)
from ..sources.types import SourceInput
from ..sources.router import fetch_text
from ..sources.webpage import fetch_webpage_text
from ..skills.generate import classify_domain_by_llm, generate_one_skill, render_quality_report
from ..skills.gate import run_skill_gate
from ..skills.prompts import make_repo_file_selector_prompt
from ..skills.publish import publish_run_to_skills_library
from ..utils.http import HttpError
from ..utils.fs import ensure_dir, make_run_dir, write_json_atomic
from ..utils.hashing import sha256_hex
from ..utils.lang import resolve_output_language
from ..utils.time import utc_iso_z, utc_now_iso_z
try:
    from .validate_skills import validate_skills
except ImportError:
    validate_skills = None


STAGE_ORDER = ["discover", "ingest", "preprocess", "llm_generate", "validate", "improve", "publish"]

_STACKOVERFLOW_QID_RE = re.compile(r"^/(?:questions|q)/(\d+)(?:/|$)")


def _parse_stackoverflow_question_id(url: str) -> int:
    u = str(url or "").strip()
    if not u:
        return 0
    try:
        p = urlparse(u)
    except Exception:
        return 0
    if str(p.netloc or "").lower() not in {"stackoverflow.com", "www.stackoverflow.com"}:
        return 0
    m = _STACKOVERFLOW_QID_RE.match(str(p.path or ""))
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _compute_backoff_seconds(attempts: int, base_seconds: int, cap_seconds: int) -> int:
    a = max(1, int(attempts or 1))
    base = max(1, int(base_seconds or 1))
    cap = max(base, int(cap_seconds or base))
    raw = base * (2 ** (a - 1))
    return int(min(cap, max(base, raw)))


def _chunk_ints(values: list[int], *, size: int) -> list[list[int]]:
    s = max(1, int(size or 1))
    return [values[i : i + s] for i in range(0, len(values), s)]


def _process_forum_ingest_batch(
    *,
    repo_root: Path,
    queue: QueueStore,
    items: list[dict[str, Any]],
    settings: QueueSettings,
    rate_ms: int,
    verbose: bool,
) -> None:
    # Batch StackExchange calls to avoid quota/throttle problems (works even without API key).
    qids: list[int] = []
    item_qid: dict[int, int] = {}
    item_extra: dict[int, dict[str, Any]] = {}

    for item in items:
        item_id = int(item.get("id") or 0)
        if item_id <= 0:
            continue
        extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})
        qid = int(extra.get("question_id") or 0)
        if not qid:
            qid = _parse_stackoverflow_question_id(str(item.get("source_url") or ""))
            if qid:
                extra["question_id"] = qid
                queue.update_item_fields(item_id, extra=extra)
        if not qid:
            msg = "Missing question_id for forum task"
            attempts = int(item.get("attempts") or 0)
            backoff = _compute_backoff_seconds(attempts, settings.backoff_base_seconds, settings.backoff_max_seconds)
            queue.nack(item_id, reason=msg, backoff_seconds=backoff, max_attempts=None)
            continue
        qids.append(qid)
        item_qid[item_id] = qid
        item_extra[item_id] = extra

    if not qids:
        return

    uniq_qids = sorted(set(qids))
    questions: dict[int, Any] = {}
    try:
        chunks = _chunk_ints(uniq_qids, size=100)
        for idx, chunk in enumerate(chunks):
            for q in stack_fetch_questions_with_body(question_ids=chunk):
                qid = int(getattr(q, "question_id", 0) or 0)
                if qid > 0:
                    questions[qid] = q
            if idx + 1 < len(chunks):
                time.sleep(0.5)
    except Exception as e:
        msg = str(e)
        retry_after_s = 0
        m = re.search(r"retry_after=(\\d+)s", msg, flags=re.IGNORECASE)
        if m:
            try:
                retry_after_s = int(m.group(1))
            except Exception:
                retry_after_s = 0
        # API is throttled/unavailable; fall back to StackPrinter (HTML export) per question.
        for item in items:
            item_id = int(item.get("id") or 0)
            if item_id <= 0:
                continue
            qid = int(item_qid.get(item_id) or 0)
            source_type = str(item.get("source_type") or "").strip().lower()
            url = str(item.get("source_url") or "").strip()
            extra = dict(item_extra.get(item_id) or {})
            try:
                res = fetch_stackprinter_text(qid, timeout_ms=20_000)
                run_dir = _ensure_run_dir(repo_root, item, queue)
                src = write_source_artifact(
                    run_dir=run_dir,
                    source_type=source_type or "webpage",
                    url=str(res.final_url or url),
                    title=str(res.title or ""),
                    raw_text=res.raw_html,
                    extracted_text=res.extracted_text,
                    license_spdx="CC-BY-SA-4.0",
                    license_risk="attribution_required",
                    extra={**extra, "stackoverflow_question_id": qid, "mode": "stackprinter"},
                )
                queue.update_source_registry(
                    source_id=src.source_id,
                    source_url=src.url,
                    source_type=source_type or "webpage",
                    license_spdx=src.license_spdx,
                    license_risk=src.license_risk,
                    status="active",
                )
                payload_path = (Path(run_dir) / "sources" / f"{src.source_id}.json").as_posix()
                queue.update_item_fields(item_id, payload_path=payload_path, source_title=src.title, extra=extra)
                queue.complete_attempt(item_id, status="ok")
                queue.requeue(item_id, new_stage="preprocess")
            except Exception as e2:
                reason = f"{msg} | stackprinter_failed: {type(e2).__name__}: {e2}"
                attempts = int(item.get("attempts") or 0)
                backoff = _compute_backoff_seconds(attempts, settings.backoff_base_seconds, settings.backoff_max_seconds)
                if retry_after_s > 0:
                    backoff = max(backoff, retry_after_s)
                queue.nack(item_id, reason=reason, backoff_seconds=backoff, max_attempts=None)
            if rate_ms and rate_ms > 0:
                time.sleep(max(0.0, float(rate_ms) / 1000.0))
        return

    accepted_answer_ids = sorted(
        {
            int(getattr(q, "accepted_answer_id", 0) or 0)
            for q in questions.values()
            if int(getattr(q, "accepted_answer_id", 0) or 0) > 0
        }
    )
    answers_by_id: dict[int, Any] = {}
    if accepted_answer_ids:
        try:
            chunks = _chunk_ints(accepted_answer_ids, size=100)
            for idx, chunk in enumerate(chunks):
                for a in stack_fetch_answers_by_id_with_body(answer_ids=chunk):
                    aid = int(getattr(a, "answer_id", 0) or 0)
                    if aid > 0:
                        answers_by_id[aid] = a
                if idx + 1 < len(chunks):
                    time.sleep(0.5)
        except Exception:
            answers_by_id = {}

    for item in items:
        item_id = int(item.get("id") or 0)
        if item_id <= 0:
            continue
        url = str(item.get("source_url") or "").strip()
        domain = str(item.get("domain") or "").strip()
        source_type = str(item.get("source_type") or "").strip().lower()
        extra = dict(item_extra.get(item_id) or {})
        qid = int(item_qid.get(item_id) or 0)
        t0 = time.time()
        if verbose:
            print(f"[{utc_now_iso_z()}] START stage=ingest id={item_id} type={source_type} url={url}", flush=True)
        try:
            q = questions.get(qid)
            if not q:
                raise RuntimeError(f"Question not found: {qid}")
            accepted_id = int(getattr(q, "accepted_answer_id", 0) or 0)
            a = answers_by_id.get(accepted_id) if accepted_id > 0 else None
            extracted = combine_question_answer_text(q, a)

            run_dir = _ensure_run_dir(repo_root, item, queue)
            src = write_source_artifact(
                run_dir=run_dir,
                source_type=source_type or "webpage",
                url=str(getattr(q, "link", "") or url),
                title=str(getattr(q, "title", "") or ""),
                raw_text=extracted,
                extracted_text=extracted,
                license_spdx="CC-BY-SA-4.0",
                license_risk="attribution_required",
                extra={
                    **extra,
                    "stackoverflow_question_id": qid,
                    "accepted_answer_id": accepted_id,
                    "answer_id": int(getattr(a, "answer_id", 0) or 0) if a else 0,
                    "domain": domain,
                },
            )
            queue.update_source_registry(
                source_id=src.source_id,
                source_url=src.url,
                source_type=source_type or "webpage",
                license_spdx=src.license_spdx,
                license_risk=src.license_risk,
                status="active",
            )
            payload_path = (Path(run_dir) / "sources" / f"{src.source_id}.json").as_posix()
            queue.update_item_fields(item_id, payload_path=payload_path, source_title=src.title, extra=extra)
            queue.complete_attempt(item_id, status="ok")
            queue.requeue(item_id, new_stage="preprocess")
            if verbose:
                dt_ms = int((time.time() - t0) * 1000)
                print(f"[{utc_now_iso_z()}] OK    stage=ingest id={item_id} ms={dt_ms}", flush=True)
        except Exception as e:
            msg = str(e)
            attempts = int(item.get("attempts") or 0)
            backoff = _compute_backoff_seconds(attempts, settings.backoff_base_seconds, settings.backoff_max_seconds)
            outcome = queue.nack(item_id, reason=msg, backoff_seconds=backoff, max_attempts=None).get("status")
            if verbose:
                dt_ms = int((time.time() - t0) * 1000)
                print(f"[{utc_now_iso_z()}] {str(outcome or 'REQUEUE').upper():5} stage=ingest id={item_id} ms={dt_ms} err={msg}", flush=True)
            else:
                if str(outcome or "") == "dead":
                    print(f"ERROR: {source_type} {url}: {msg}", flush=True)

        if rate_ms and rate_ms > 0:
            time.sleep(max(0.0, float(rate_ms) / 1000.0))


def _canonicalize(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        return canonicalize_source_url(u) or u
    except Exception:
        return u


def _collect_domains(*, all_domains: bool, domain: str | None) -> list[str]:
    all_names = sorted(DOMAIN_CONFIG.keys())
    if all_domains:
        return all_names
    d = str(domain or "").strip().lower()
    if d:
        return [d]
    return all_names


def _ensure_run_dir(repo_root: Path, item: dict[str, Any], queue: QueueStore) -> Path:
    run_id = str(item.get("run_id") or "").strip()
    if run_id:
        run_dir = (repo_root / "captures" / run_id).resolve()
        ensure_dir(run_dir)
        return run_dir

    topic = f"queue-{item.get('source_type')}-{str(item.get('source_id') or '')[:8]}"
    run_dir = make_run_dir(repo_root, topic)
    ensure_dir(run_dir)
    queue.update_item_fields(int(item["id"]), run_id=run_dir.name)
    return run_dir


def _resolve_payload_path(
    *,
    repo_root: Path,
    payload_path: str,
    run_id: str,
    source_id: str,
) -> Path | None:
    raw = str(payload_path or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        if p.exists():
            return p
        raw_norm = raw.replace("\\", "/")
        marker = "/captures/"
        if marker in raw_norm:
            tail = raw_norm.split(marker, 1)[1]
            cand = (repo_root / "captures" / tail).resolve()
            if cand.exists():
                return cand
    if run_id and source_id:
        cand = (repo_root / "captures" / run_id / "sources" / f"{source_id}.json").resolve()
        if cand.exists():
            return cand
    return None


def _load_source_artifact(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Source artifact not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


@contextmanager
def _acquire_manifest_lock(run_dir: Path) -> Any:
    if fcntl is None:
        yield
        return
    lock_path = run_dir / ".manifest.lock"
    ensure_dir(run_dir)
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


def _normalize_manifest_method(source_type: str) -> str:
    t = str(source_type or "").strip().lower()
    if t in {"github", "git", "repo"}:
        return "github"
    if t in {"forum", "stack", "stackoverflow"}:
        return "forum"
    return "web"


def _update_run_manifest_for_skill(
    *,
    run_dir: Path,
    domain: str,
    source_type: str,
    skill: dict[str, Any],
    artifact_id: str,
    source_fetched_at: str,
    topic_input: str,
) -> None:
    manifest_path = run_dir / "manifest.json"
    with _acquire_manifest_lock(run_dir):
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                obj = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    manifest = obj
            except Exception:
                manifest = {}

        if not isinstance(manifest.get("domains"), list):
            manifest["schema_version"] = 1
            manifest["run_id"] = run_dir.name
            manifest["topic_input"] = str(topic_input or "")
            manifest["generated_at"] = utc_now_iso_z()
            manifest["cli_options"] = manifest.get("cli_options") if isinstance(manifest.get("cli_options"), dict) else {}
            manifest["domains"] = []
            manifest["domain_config"] = DOMAIN_CONFIG

        domains = manifest.get("domains")
        if not isinstance(domains, list):
            domains = []
            manifest["domains"] = domains

        domain_key = str(domain or "").strip() or "unknown"
        domain_entry: dict[str, Any] | None = None
        for d in domains:
            if isinstance(d, dict) and str(d.get("domain") or "").strip() == domain_key:
                domain_entry = d
                break
        if domain_entry is None:
            domain_entry = {
                "domain": domain_key,
                "topic_input": str(topic_input or ""),
                "counts_requested": {"web": 0, "github": 0, "forum": 0},
                "web": [],
                "github": [],
                "forum": [],
                "web_errors": [],
                "github_errors": [],
                "forum_errors": [],
            }
            domains.append(domain_entry)

        for k in ("web", "github", "forum"):
            if not isinstance(domain_entry.get(k), list):
                domain_entry[k] = []

        method_key = _normalize_manifest_method(source_type)
        arr: list[dict[str, Any]] = list(domain_entry.get(method_key) or [])
        skill_id = str(skill.get("id") or "")
        rel_dir = str(skill.get("rel_dir") or "")
        arr = [
            x
            for x in arr
            if not (
                (skill_id and str(x.get("id") or "") == skill_id)
                or (rel_dir and str(x.get("rel_dir") or "") == rel_dir)
            )
        ]
        entry = {
            "id": skill_id,
            "title": str(skill.get("title") or ""),
            "domain": domain_key,
            "topic": str(skill.get("topic") or ""),
            "slug": str(skill.get("slug") or ""),
            "rel_dir": rel_dir,
            "source_type": str(source_type or ""),
            "source_url": str(skill.get("source_url") or ""),
            "source_artifact_id": str(artifact_id or ""),
            "source_fetched_at": str(source_fetched_at or ""),
            "generated_at": str(skill.get("generated_at") or ""),
            "review": skill.get("review") if isinstance(skill.get("review"), dict) else {},
            "lint_issues": skill.get("lint_issues") if isinstance(skill.get("lint_issues"), list) else [],
        }
        arr.append(entry)
        domain_entry[method_key] = arr
        domain_entry["counts_requested"] = {
            "web": len(domain_entry.get("web") or []),
            "github": len(domain_entry.get("github") or []),
            "forum": len(domain_entry.get("forum") or []),
        }
        manifest["domains"] = domains
        manifest["domain_config"] = DOMAIN_CONFIG

        write_json_atomic(manifest_path, manifest)
        render_quality_report(run_dir=run_dir, run_manifest=manifest)


def _is_github_repo_root_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    host = str(p.netloc or "").strip().lower()
    if host != "github.com":
        return False
    segs = [s for s in str(p.path or "").split("/") if s]
    return len(segs) == 2


def _github_candidate_score(*, path: str, tags: list[str], language: str, size_bytes: int, max_bytes: int) -> int:
    p = str(path or "").lower()
    score = 0

    # Prefer implementation files.
    tag_w = {
        "src": 70,
        "script": 55,
        "config": 40,
        "ci": 25,
        "doc": 12,
        "test": 8,
        "other": 0,
    }
    for t in tags:
        score += int(tag_w.get(str(t), 0))

    # Prefer code languages over pure docs/config.
    lang_w = {
        "python": 30,
        "go": 28,
        "rust": 28,
        "typescript": 24,
        "javascript": 20,
        "java": 18,
        "cpp": 18,
        "shell": 12,
        "yaml": 10,
        "toml": 10,
        "json": 8,
        "markdown": 6,
        "text": 2,
    }
    score += int(lang_w.get(str(language or "").lower(), 0))

    # Keyword boosts (debuggable + likely skill-worthy).
    for kw, w in [
        ("cli", 25),
        ("runner", 22),
        ("queue", 18),
        ("pipeline", 18),
        ("crawler", 14),
        ("fetch", 14),
        ("ingest", 12),
        ("validate", 12),
        ("skill", 10),
    ]:
        if kw in p:
            score += w

    # Penalize tiny/huge-ish files.
    n = int(size_bytes or 0)
    if n and n < 200:
        score -= 45
    elif n and n < 800:
        score -= 12
    if n and max_bytes and n > int(max_bytes * 0.9):
        score -= 15

    # Prefer shallower paths.
    score -= min(18, p.count("/"))
    return score


def _try_github_repo_fanout(
    *,
    repo_root: Path,
    run_dir: Path,
    item: dict[str, Any],
    queue: QueueStore,
    llm,
    settings: QueueSettings,
    license_spdx: str,
    license_risk: str,
) -> bool:
    if int(settings.github_repo_fanout_n or 0) <= 0:
        return False
    if queue.is_draining():
        return False

    url = str(item.get("source_url") or "").strip()
    if not _is_github_repo_root_url(url):
        return False

    extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})
    full_name = str(extra.get("repo") or "").strip() or parse_github_full_name_from_url(url)
    if not full_name:
        return False

    default_branch = str(extra.get("default_branch") or "main").strip()
    repo_url, commit_sha, blobs = fetch_repo_tree(full_name=full_name, ref=default_branch)

    max_bytes = int(settings.github_repo_fanout_max_file_bytes or 80_000)
    excluded_dirs = set(DEFAULT_EXCLUDE_DIRS)
    excluded_files = set(DEFAULT_EXCLUDE_FILES)

    skipped: dict[str, int] = {"excluded": 0, "binary": 0, "too_big": 0, "bad_path": 0}
    candidates: list[dict[str, Any]] = []

    for b in blobs:
        p = str(getattr(b, "path", "") or "").replace("\\", "/").lstrip("/")
        if not p:
            skipped["bad_path"] += 1
            continue
        if Path(p).name in excluded_files or any(part in excluded_dirs for part in p.split("/")):
            skipped["excluded"] += 1
            continue
        if is_probably_binary_path(p):
            skipped["binary"] += 1
            continue
        size = int(getattr(b, "size_bytes", 0) or 0)
        if size and max_bytes and size > max_bytes:
            skipped["too_big"] += 1
            continue

        language = detect_language(p)
        tags = classify_tags(p)
        score = _github_candidate_score(path=p, tags=tags, language=language, size_bytes=size, max_bytes=max_bytes)
        candidates.append(
            {
                "path": p,
                "blob_sha": str(getattr(b, "blob_sha", "") or ""),
                "size_bytes": size,
                "language": language,
                "tags": tags,
                "score": int(score),
            }
        )

    if not candidates:
        return False

    candidates.sort(key=lambda r: (-int(r.get("score") or 0), str(r.get("path") or "")))

    target_n = max(1, int(settings.github_repo_fanout_n))
    try:
        raw_mul = str(os.environ.get("GITHUB_REPO_FANOUT_POOL_MULTIPLIER") or "").strip()
        pool_mul = int(raw_mul) if raw_mul else 8
    except Exception:
        pool_mul = 8
    pool_mul = max(1, min(20, int(pool_mul)))
    pool_n = max(target_n, int(target_n * pool_mul))
    pool_n = min(pool_n, len(candidates))
    chosen: list[dict[str, Any]] = []
    selection: dict[str, Any] = {"mode": "heuristic"}

    if str(settings.github_repo_fanout_select or "").strip().lower() == "llm" and llm is not None:
        readme = ""
        docs_summary = ""
        try:
            readme = github_fetch_readme_excerpt_raw(full_name=full_name, default_branch=default_branch)
            docs_summary = combine_repo_text(
                GithubRepo(
                    full_name=full_name,
                    html_url=repo_url,
                    description=str(extra.get("description") or "").strip(),
                    stargazers_count=int(extra.get("stars") or 0),
                    language=str(extra.get("language") or ""),
                    default_branch=default_branch,
                    license_spdx=license_spdx,
                ),
                readme,
            )
        except Exception:
            readme = ""
            docs_summary = str(extra.get("description") or "").strip()

        prompt_max = max(1, int(settings.github_repo_fanout_prompt_max_files or 300))
        files_for_llm = [
            {k: v for k, v in c.items() if k in {"path", "size_bytes", "language", "tags", "score"}}
            for c in candidates[:prompt_max]
        ]
        output_language = resolve_output_language(default="en")
        msgs = make_repo_file_selector_prompt(
            language=output_language,
            top_n=pool_n,
            files=files_for_llm,
            docs_summary=docs_summary,
        )

        try:
            timeout_ms = int(str(os.environ.get("LANGSKILLS_LLM_TIMEOUT_MS") or "").strip() or 300_000)
        except Exception:
            timeout_ms = 300_000

        try:
            out = llm.chat_json(messages=msgs, temperature=0.0, timeout_ms=timeout_ms)
            selection = {"mode": "llm", "response": out}
            cand_by_path = {str(c.get("path") or ""): c for c in candidates}
            raw_files = out.get("files") if isinstance(out, dict) else None
            if isinstance(raw_files, list):
                seen: set[str] = set()
                for fc in raw_files:
                    if not isinstance(fc, dict):
                        continue
                    path = str(fc.get("path") or "").strip()
                    if not path or path in seen or path not in cand_by_path:
                        continue
                    seen.add(path)
                    base = dict(cand_by_path[path])
                    base["llm_reason"] = str(fc.get("reason") or "").strip()
                    base["llm_priority_score"] = int(fc.get("priority_score") or 0)
                    chosen.append(base)
                    if len(chosen) >= pool_n:
                        break
        except Exception as e:
            selection = {"mode": "llm_failed", "error": str(e), "error_type": type(e).__name__}
            chosen = []

    if not chosen:
        chosen = [dict(c) for c in candidates[:pool_n]]

    # Fan out into child queue items, one per file.
    item_id = int(item.get("id") or 0)
    run_id = str(item.get("run_id") or run_dir.name).strip() or run_dir.name
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    config_snapshot = item.get("config_snapshot") if isinstance(item.get("config_snapshot"), dict) else {}
    domain = str(item.get("domain") or "").strip()

    fanout_dir = run_dir / "github_repo_fanout" / str(item.get("source_id") or "")[:16]
    ensure_dir(fanout_dir)

    enqueued: list[dict[str, Any]] = []
    enqueue_stats: dict[str, int] = {"ok": 0, "skipped": 0, "drain": 0, "error": 0}
    child_priority = int(item.get("priority") or 0) + 10

    for c in chosen:
        path = str(c.get("path") or "").strip()
        if not path:
            continue
        owner, repo = full_name.split("/", 1)
        blob_url = f"https://github.com/{owner}/{repo}/blob/{commit_sha}/{quote(path, safe='/')}"
        child_extra = {
            **extra,
            "repo": full_name,
            "license_spdx": license_spdx,
            "github_kind": "blob",
            "github_commit": commit_sha,
            "github_path": path,
            "github_blob_sha": str(c.get("blob_sha") or ""),
            "github_size_bytes": int(c.get("size_bytes") or 0),
            "github_language": str(c.get("language") or ""),
            "github_tags": c.get("tags") if isinstance(c.get("tags"), list) else [],
            "github_parent_source_id": str(item.get("source_id") or ""),
            "github_parent_item_id": int(item_id or 0),
        }
        try:
            res = queue.enqueue(
                source_id="",
                source_type="github",
                source_url=blob_url,
                source_title=f"{full_name}:{path}",
                stage="ingest",
                priority=child_priority,
                max_attempts=int(item.get("max_attempts") or settings.max_attempts),
                domain=domain,
                tags=tags,
                config_snapshot=config_snapshot,
                extra=child_extra,
                run_id=run_id,
                trace_id=str(item.get("trace_id") or ""),
            )
            if bool(res.get("enqueued")):
                enqueue_stats["ok"] += 1
                enqueued.append({"path": path, "url": blob_url, "item_id": int(res.get("id") or 0)})
            else:
                reason = str(res.get("reason") or "").strip().lower()
                if reason == "drain_enabled":
                    enqueue_stats["drain"] += 1
                else:
                    enqueue_stats["skipped"] += 1
        except Exception:
            enqueue_stats["error"] += 1

    # Persist selection info for debugging/audit.
    write_json_atomic(
        fanout_dir / "fanout.json",
        {
            "source_url": url,
            "repo_url": repo_url,
            "full_name": full_name,
            "ref": default_branch,
            "commit_sha": commit_sha,
            "settings": {
                "fanout_n": int(settings.github_repo_fanout_n),
                "pool_multiplier": int(pool_mul),
                "pool_n": int(pool_n),
                "select": str(settings.github_repo_fanout_select),
                "max_file_bytes": int(settings.github_repo_fanout_max_file_bytes),
                "prompt_max_files": int(settings.github_repo_fanout_prompt_max_files),
            },
            "filters": {"skipped": skipped, "candidates_total": len(candidates)},
            "selection": selection,
            "candidates_sample": candidates[: min(len(candidates), int(settings.github_repo_fanout_prompt_max_files or 300))],
            "selected": chosen,
            "enqueue": {"stats": enqueue_stats, "items": enqueued, "child_priority": int(child_priority)},
        },
    )

    # Record license info for the parent repo and close it.
    if item_id > 0:
        queue.update_source_registry(
            source_id=str(item.get("source_id") or ""),
            source_url=url,
            source_type="github",
            license_spdx=license_spdx,
            license_risk=license_risk,
            status="active",
        )
        try:
            rel_trace = (fanout_dir / "fanout.json").relative_to(run_dir)
            queue.update_item_fields(item_id, trace_id=str(rel_trace).replace("\\", "/"))
        except Exception:
            pass
        queue.ack(item_id)

    return True


def _discover_tasks(
    *,
    domains: list[str],
    topic_override: str | None,
    topic_tags: list[str] | None,
    queue: QueueStore,
    repo_root: Path,
    max_attempts: int,
    discover_providers: set[str],
    ignore_license_policy: bool,
    verbose: bool,
) -> None:
    policy = read_license_policy(repo_root)
    draining = bool(queue.is_draining())

    github_throttle_wait_s = 0
    if "github" in discover_providers and str(os.environ.get("LANGSKILLS_GITHUB_DISABLE_GLOBAL_THROTTLE") or "").strip() != "1":
        lock_path = repo_root / "runs" / "github_search_rate.lock"
        try:
            raw = lock_path.read_text(encoding="utf-8").strip()
            next_ts = float(raw) if raw else 0.0
        except Exception:
            next_ts = 0.0
        github_throttle_wait_s = int(max(0.0, next_ts - time.time()))
        if github_throttle_wait_s > 0 and verbose:
            print(
                f"[{utc_now_iso_z()}] WARN: GitHub search throttled; skipping github discovery for ~{github_throttle_wait_s}s",
                flush=True,
            )

    for d in domains:
        cfg = DOMAIN_CONFIG.get(d)
        if not isinstance(cfg, dict):
            continue
        topic = str(topic_override or cfg.get("default_topic") or d).strip() or d
        tags = [str(t).strip() for t in (topic_tags or []) if str(t).strip()]
        config_snapshot = {"domain": d, "topic": topic, "tags": tags}

        web_seeded = web_enqueued = web_skipped_policy = web_blocked_drain = web_dupe = 0
        gh_found = gh_enqueued = gh_skipped_policy = gh_skipped_license = gh_blocked_drain = gh_dupe = 0
        forum_found = forum_enqueued = forum_skipped_policy = forum_blocked_drain = forum_dupe = 0

        def _count_enqueue_result(res: dict[str, Any]) -> tuple[int, int, int]:
            if bool(res.get("enqueued")):
                return (1, 0, 0)
            reason = str(res.get("reason") or "").strip().lower()
            if reason == "drain_enabled":
                return (0, 1, 0)
            if reason:
                return (0, 0, 1)
            return (0, 0, 0)

        # Web seeds
        if "webpage" in discover_providers:
            web_policy = get_crawl_policy_from_config(cfg, "webpage")
            for url in cfg.get("web_urls") if isinstance(cfg.get("web_urls"), list) else []:
                url0 = str(url or "").strip()
                canon = _canonicalize(url0) or url0
                if not canon:
                    continue
                if not is_url_allowed_by_host_policy(canon, web_policy):
                    print(f"SKIP: blocked by crawl policy (webpage): {canon}")
                    web_skipped_policy += 1
                    continue
                web_seeded += 1
                res = queue.enqueue(
                    source_id=sha256_hex(canon),
                    source_type="webpage",
                    source_url=canon,
                    source_title="",
                    stage="ingest",
                    priority=0,
                    max_attempts=max_attempts,
                    domain=d,
                    tags=tags,
                    config_snapshot=config_snapshot,
                    extra={"topic": topic, "original_url": url0} if url0 and url0 != canon else {"topic": topic},
                )
                e, dr, du = _count_enqueue_result(res)
                web_enqueued += e
                web_blocked_drain += dr
                web_dupe += du

        # GitHub search
        if "github" in discover_providers:
            if github_throttle_wait_s > 0:
                continue
            gh_items: list[GithubRepo] = []
            try:
                min_stars = int(cfg.get("github", {}).get("min_stars") or 0)
                pushed_after = str(cfg.get("github", {}).get("pushed_after") or "").strip()
                gh_q = f"{cfg.get('github', {}).get('query', '')} {topic} stars:>{min_stars}".strip()
                if pushed_after:
                    gh_q = f"{gh_q} pushed:>{pushed_after}".strip()
                gh_items = github_search_top_repos(
                    query=gh_q,
                    per_page=10,
                    min_stars=min_stars,
                    pushed_after=pushed_after or None,
                    skip_if_throttled=True,
                )
            except HttpError as e:
                print(f"WARN: GitHub search failed (HTTP {e.status}): {e}")
                gh_items = []
            except Exception as e:
                print(f"WARN: GitHub search failed: {e}")
                gh_items = []

            gh_policy = get_crawl_policy_from_config(cfg, "github")
            gh_found += len(gh_items)
            for repo in gh_items:
                url = _canonicalize(repo.html_url) or repo.html_url
                if not url or not is_url_allowed_by_host_policy(url, gh_policy):
                    print(f"SKIP: blocked by crawl policy (github): {url}")
                    gh_skipped_policy += 1
                    continue
                spdx = str(repo.license_spdx or "").strip()
                if not ignore_license_policy and license_decision(policy, source_type="github", license_spdx=spdx) == "deny":
                    print(f"SKIP: denied license repo ({spdx or 'unknown'}): {url}")
                    gh_skipped_license += 1
                    continue
                res = queue.enqueue(
                    source_id=sha256_hex(url),
                    source_type="github",
                    source_url=url,
                    source_title=repo.full_name,
                    stage="ingest",
                    priority=0,
                    max_attempts=max_attempts,
                    domain=d,
                    tags=tags,
                    config_snapshot=config_snapshot,
                    extra={
                        "topic": topic,
                        "repo": repo.full_name,
                        "description": repo.description,
                        "default_branch": repo.default_branch,
                        "stars": repo.stargazers_count,
                        "language": repo.language,
                        "license_spdx": repo.license_spdx,
                    },
                )
                e, dr, du = _count_enqueue_result(res)
                gh_enqueued += e
                gh_blocked_drain += dr
                gh_dupe += du

        # Forum search
        if "forum" in discover_providers:
            top_qs = []
            try:
                forum_q = " ".join([topic, str(cfg.get("forum", {}).get("query") or "").strip()]).strip()
                top_qs = stack_search_top_questions(
                    q=forum_q,
                    tagged=str(cfg.get("forum", {}).get("tagged") or "").strip() or None,
                    pagesize=10,
                )
            except Exception as e:
                print(f"WARN: Forum search failed: {e}")
                top_qs = []

            forum_policy = get_crawl_policy_from_config(cfg, "forum")
            forum_found += len(top_qs)
            for q0 in top_qs:
                url = _canonicalize(q0.link) or q0.link
                if not url or not is_url_allowed_by_host_policy(url, forum_policy):
                    print(f"SKIP: blocked by crawl policy (forum): {url}")
                    forum_skipped_policy += 1
                    continue
                res = queue.enqueue(
                    source_id=sha256_hex(url),
                    source_type="forum",
                    source_url=url,
                    source_title=q0.title,
                    stage="ingest",
                    priority=0,
                    max_attempts=max_attempts,
                    domain=d,
                    tags=tags,
                    config_snapshot=config_snapshot,
                    extra={"topic": topic, "question_id": int(q0.question_id or 0)},
                )
                e, dr, du = _count_enqueue_result(res)
                forum_enqueued += e
                forum_blocked_drain += dr
                forum_dupe += du

        if verbose:
            parts: list[str] = []
            if "github" in discover_providers:
                parts.append(f"github_found={gh_found} github_enqueued={gh_enqueued}")
                if gh_skipped_policy:
                    parts.append(f"github_skipped_policy={gh_skipped_policy}")
                if gh_skipped_license:
                    parts.append(f"github_skipped_license={gh_skipped_license}")
                if gh_dupe:
                    parts.append(f"github_dupe={gh_dupe}")
                if gh_blocked_drain:
                    parts.append(f"github_drain_blocked={gh_blocked_drain}")
            if "webpage" in discover_providers:
                parts.append(f"web_seeded={web_seeded} web_enqueued={web_enqueued}")
                if web_skipped_policy:
                    parts.append(f"web_skipped_policy={web_skipped_policy}")
                if web_dupe:
                    parts.append(f"web_dupe={web_dupe}")
                if web_blocked_drain:
                    parts.append(f"web_drain_blocked={web_blocked_drain}")
            if "forum" in discover_providers:
                parts.append(f"forum_found={forum_found} forum_enqueued={forum_enqueued}")
                if forum_skipped_policy:
                    parts.append(f"forum_skipped_policy={forum_skipped_policy}")
                if forum_dupe:
                    parts.append(f"forum_dupe={forum_dupe}")
                if forum_blocked_drain:
                    parts.append(f"forum_drain_blocked={forum_blocked_drain}")
            print(
                f"[{utc_now_iso_z()}] DISCOVER domain={d} topic={topic} drain={1 if draining else 0} " + " ".join(parts),
                flush=True,
            )


def _process_item(
    *,
    repo_root: Path,
    item: dict[str, Any],
    queue: QueueStore,
    llm,
    publish_overwrite: bool,
    strict: bool,
    settings: QueueSettings,
    ignore_license_policy: bool = False,
    worker_id: str = "",
    verbose: bool = False,
) -> None:
    stage = str(item.get("stage") or "").strip().lower()
    source_type = str(item.get("source_type") or "").strip().lower()
    url = str(item.get("source_url") or "").strip()
    title = str(item.get("source_title") or "").strip()
    domain = str(item.get("domain") or "").strip()
    extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})

    if stage == "discover":
        queue.complete_attempt(int(item["id"]), status="ok")
        queue.requeue(int(item["id"]), new_stage="ingest")
        return

    if stage == "ingest":
        run_dir = _ensure_run_dir(repo_root, item, queue)
        item_id = int(item.get("id") or 0)
        run_id = str(item.get("run_id") or run_dir.name).strip() or run_dir.name
        source_id = str(item.get("source_id") or "").strip()
        payload_path = str(item.get("payload_path") or "").strip()
        resolved = _resolve_payload_path(
            repo_root=repo_root,
            payload_path=payload_path,
            run_id=run_id,
            source_id=source_id,
        )
        if resolved is not None:
            if str(resolved.as_posix()) != str(payload_path or ""):
                queue.update_item_fields(item_id, payload_path=resolved.as_posix())
            queue.complete_attempt(item_id, status="ok")
            queue.requeue(item_id, new_stage="preprocess")
            return

        raw_text = ""
        extracted_text = ""
        license_spdx = ""
        license_risk = "unknown"
        policy = read_license_policy(repo_root)
        artifact_url = url

        if source_type == "webpage":
            r = fetch_text(url, engine="auto")
            raw_text = r.raw_html
            extracted_text = r.extracted_text
            final_url = str(getattr(r, "final_url", "") or "").strip()
            if final_url and final_url != url:
                artifact_url = final_url
                extra = {**extra, "original_url": url, "resolved_url": final_url}
        elif source_type in {"zhihu", "xhs", "web", "baidu"}:
            r = fetch_text(url, engine=source_type if source_type in {"zhihu", "xhs"} else "auto")
            raw_text = r.raw_html
            extracted_text = r.extracted_text
            final_url = str(getattr(r, "final_url", "") or "").strip()
            if final_url and final_url != url:
                artifact_url = final_url
                extra = {**extra, "original_url": url, "resolved_url": final_url}
        elif source_type == "github":
            license_spdx = str(extra.get("license_spdx") or "").strip()
            decision = license_decision(policy, source_type="github", license_spdx=license_spdx)
            if license_spdx:
                license_risk = str(decision or "unknown")
            if decision == "deny" and not ignore_license_policy:
                queue.update_source_registry(
                    source_id=str(item.get("source_id") or ""),
                    source_url=url,
                    source_type=source_type,
                    license_spdx=license_spdx,
                    license_risk="deny",
                    status="license_fail",
                )
                raise RuntimeError(f"license_denied ({license_spdx or 'unknown'})")
            blob = parse_github_blob_url(url)
            if blob:
                full_name, ref, path = blob
                content, meta = github_fetch_blob_raw_text(
                    full_name=full_name,
                    ref=ref,
                    path=path,
                    timeout_ms=20_000,
                    max_bytes=int(settings.github_repo_fanout_max_file_bytes or 80_000),
                )
                raw_text = content
                extracted_text = content
                title = title or f"{full_name}:{path}"
                extra = {**extra, "repo": full_name, "github_kind": "blob", "github_ref": ref, "github_path": path, **meta}
            else:
                if _try_github_repo_fanout(
                    repo_root=repo_root,
                    run_dir=run_dir,
                    item=item,
                    queue=queue,
                    llm=llm,
                    settings=settings,
                    license_spdx=license_spdx,
                    license_risk=license_risk,
                ):
                    return

                repo = str(extra.get("repo") or "").strip() or parse_github_full_name_from_url(url)
                desc = str(extra.get("description") or "").strip()
                default_branch = str(extra.get("default_branch") or "main").strip()
                readme = github_fetch_readme_excerpt_raw(full_name=repo, default_branch=default_branch)
                combined = combine_repo_text(
                    GithubRepo(
                        full_name=repo,
                        html_url=url,
                        description=desc,
                        stargazers_count=int(extra.get("stars") or 0),
                        language=str(extra.get("language") or ""),
                        default_branch=default_branch,
                        license_spdx=license_spdx,
                    ),
                    readme,
                )
                raw_text = combined
                extracted_text = combined
                title = title or repo
        elif source_type == "forum":
            license_spdx = "CC-BY-SA-4.0"
            license_risk = "attribution_required"
            qid = int(extra.get("question_id") or 0)
            if not qid:
                qid = _parse_stackoverflow_question_id(url)
                if qid:
                    extra = {**extra, "question_id": qid}
                    queue.update_item_fields(int(item["id"]), extra=extra)
                else:
                    raise RuntimeError("Missing question_id for forum task")
            try:
                q_arr = stack_fetch_questions_with_body(question_ids=[qid])
                a_arr = stack_fetch_answers_with_body(question_ids=[qid])
                q0 = q_arr[0] if q_arr else None
                if not q0:
                    raise RuntimeError(f"Question not found: {qid}")
                title = q0.title
                ans = pick_answer_for_question(q0, a_arr)
                extracted_text = combine_question_answer_text(q0, ans)
                raw_text = extracted_text
                extra = {**extra, "stackoverflow_question_id": qid, "accepted_answer_id": q0.accepted_answer_id}
            except Exception:
                # StackExchange API is frequently throttled; fall back to StackPrinter, then to webpage/Playwright.
                try:
                    r2 = fetch_stackprinter_text(qid, timeout_ms=20_000)
                    raw_text = r2.raw_html
                    extracted_text = r2.extracted_text
                    title = r2.title or title
                    extra = {**extra, "stackoverflow_question_id": qid, "mode": "stackprinter"}
                except Exception:
                    r = fetch_webpage_text(url)
                    raw_text = r.raw_html
                    extracted_text = r.extracted_text
                    extra = {**extra, "stackoverflow_question_id": qid, "mode": "webpage"}
        else:
            # Fallback to direct webpage fetch for unknown source types.
            r = fetch_text(url, engine="auto")
            raw_text = r.raw_html
            extracted_text = r.extracted_text

        src = write_source_artifact(
            run_dir=run_dir,
            source_type=source_type or "webpage",
            url=artifact_url,
            title=title,
            raw_text=raw_text,
            extracted_text=extracted_text,
            license_spdx=license_spdx,
            license_risk=license_risk,
            extra=extra,
        )
        queue.update_source_registry(
            source_id=src.source_id,
            source_url=src.url,
            source_type=source_type or "webpage",
            license_spdx=src.license_spdx,
            license_risk=src.license_risk,
            status="active",
        )
        payload_path = (Path(run_dir) / "sources" / f"{src.source_id}.json").as_posix()
        queue.update_item_fields(int(item["id"]), payload_path=payload_path, source_title=src.title)
        queue.complete_attempt(int(item["id"]), status="ok")
        queue.requeue(int(item["id"]), new_stage="preprocess")
        return

    if stage == "preprocess":
        item_id = int(item.get("id") or 0)
        run_dir = _ensure_run_dir(repo_root, item, queue)
        run_id = str(item.get("run_id") or run_dir.name).strip() or run_dir.name
        source_id = str(item.get("source_id") or "").strip()
        payload_path = str(item.get("payload_path") or "").strip()
        resolved = _resolve_payload_path(
            repo_root=repo_root,
            payload_path=payload_path,
            run_id=run_id,
            source_id=source_id,
        )
        if resolved is None:
            raise RuntimeError("Missing payload_path for preprocess stage")
        if str(resolved.as_posix()) != str(payload_path or ""):
            queue.update_item_fields(item_id, payload_path=resolved.as_posix())
        # Preprocess is minimal for now: ensure artifact exists and move to LLM stage.
        _ = _load_source_artifact(resolved)
        queue.complete_attempt(item_id, status="ok")
        queue.requeue(item_id, new_stage="llm_generate")
        return

    if stage == "llm_generate":
        run_dir = _ensure_run_dir(repo_root, item, queue)
        item_id = int(item.get("id") or 0)
        run_id = str(item.get("run_id") or run_dir.name).strip() or run_dir.name
        source_id = str(item.get("source_id") or "").strip()
        payload_path = str(item.get("payload_path") or "").strip()
        resolved = _resolve_payload_path(
            repo_root=repo_root,
            payload_path=payload_path,
            run_id=run_id,
            source_id=source_id,
        )
        if resolved is None:
            raise RuntimeError("Missing payload_path for llm_generate stage")
        if str(resolved.as_posix()) != str(payload_path or ""):
            queue.update_item_fields(item_id, payload_path=resolved.as_posix())
        artifact = _load_source_artifact(resolved)
        prompt_text = str(artifact.get("extracted_text") or "")
        artifact_extra = dict(artifact.get("extra") if isinstance(artifact.get("extra"), dict) else {})
        output_language = resolve_output_language(default="en")
        artifact_extra["language"] = output_language
        extra = {**extra, "language": output_language}
        artifact_id = str(artifact.get("source_id") or "").strip()
        if artifact_id:
            src_dir = run_dir / "sources"
            ensure_dir(src_dir)
            dst = src_dir / f"{artifact_id}.json"
            if not dst.exists():
                write_json_atomic(dst, artifact)

        # GitHub repo-root tasks should fan out into N file-level tasks before generation.
        if source_type == "github" and int(settings.github_repo_fanout_n or 0) > 0 and _is_github_repo_root_url(url):
            if _try_github_repo_fanout(
                repo_root=repo_root,
                run_dir=run_dir,
                item=item,
                queue=queue,
                llm=llm,
                settings=settings,
                license_spdx=str(artifact.get("license_spdx") or extra.get("license_spdx") or ""),
                license_risk=str(artifact.get("license_risk") or extra.get("license_risk") or "unknown"),
            ):
                return

        skill_rel_dir = str(extra.get("skill_rel_dir") or "").strip()
        skill_id = str(extra.get("skill_id") or "").strip()
        if skill_rel_dir:
            if (Path(run_dir) / skill_rel_dir).exists():
                queue.complete_attempt(int(item["id"]), status="ok")
                queue.requeue(int(item["id"]), new_stage="validate")
                return

        reserved_budget = False
        kind = str(extra.get("github_kind") or artifact_extra.get("github_kind") or "").strip().lower()
        worker_id_effective = str(worker_id or item.get("lease_owner") or "").strip()
        if source_type == "github" and int(settings.github_repo_fanout_n or 0) > 0 and run_id and kind == "blob":
            # Reserve BEFORE calling the gate to avoid paying for gate calls when the repo already has enough skills.
            resv = queue.reserve_run_budget(
                run_id=run_id,
                budget_key="github_repo_skills",
                item_id=item_id,
                target=int(settings.github_repo_fanout_n),
                lease_seconds=int(settings.lease_seconds),
                worker_id=worker_id_effective,
            )
            extra = {**extra, "budget": {k: resv.get(k) for k in ["reason", "target", "done", "reserved_count"]}}
            queue.update_item_fields(item_id, extra=extra)

            if not bool(resv.get("reserved")):
                done = int(resv.get("done") or 0)
                target = int(resv.get("target") or 0)
                if target > 0 and done >= target:
                    queue.ack(item_id, attempt_status="skip", attempt_error="budget_full")
                    return
                # Wait for other reserved items to complete (or free slots) without burning attempts.
                delay_s = 15
                try:
                    raw_delay = str(os.environ.get("LANGSKILLS_GITHUB_BUDGET_WAIT_SECONDS") or "").strip()
                    delay_s = int(raw_delay) if raw_delay else delay_s
                except Exception:
                    delay_s = 15
                delay_s = max(1, min(120, int(delay_s)))
                avail = utc_iso_z(_dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(seconds=delay_s))
                queue.complete_attempt(item_id, status="wait")
                queue.requeue(item_id, new_stage="llm_generate")
                queue.update_item_fields(item_id, available_at=avail)
                return

            reserved_budget = True

        gate = run_skill_gate(
            run_dir=run_dir,
            domain=domain,
            method=source_type,
            source_id=str(artifact.get("source_id") or ""),
            source_url=str(artifact.get("url") or url),
            source_title=str(artifact.get("title") or title),
            extracted_text=prompt_text,
            llm=llm,
        )
        extra = {**extra, "gate": gate}
        if item_id > 0:
            queue.update_item_fields(item_id, extra=extra)

        if not bool(gate.get("allow_generate")):
            if reserved_budget and source_type == "github" and run_id:
                try:
                    queue.release_run_budget_reservation(run_id=run_id, budget_key="github_repo_skills", item_id=item_id)
                except Exception:
                    pass
            queue.ack(item_id, attempt_status="skip", attempt_error=str(gate.get("verdict") or "gate_fail"))
            return

        base_slug = f"{domain}-{source_type}-{str(artifact.get('source_id') or '')[:10]}"
        try:
            skill = generate_one_skill(
                run_dir=run_dir,
                domain=domain,
                method=source_type,
                seq=1,
                base_slug=base_slug,
                source=SourceInput(
                    source_type=source_type,
                    url=url,
                    title=str(artifact.get("title") or title),
                    text=prompt_text,
                    fetched_at=str(artifact.get("fetched_at") or ""),
                    extra={
                        **artifact_extra,
                        "source_artifact_id": str(artifact.get("source_id") or ""),
                        "license_spdx": str(artifact.get("license_spdx") or ""),
                        "license_risk": str(artifact.get("license_risk") or ""),
                    },
                ),
                llm=llm,
            )
        except Exception:
            if reserved_budget and source_type == "github" and run_id:
                try:
                    queue.release_run_budget_reservation(run_id=run_id, budget_key="github_repo_skills", item_id=item_id)
                except Exception:
                    pass
            raise

        _update_run_manifest_for_skill(
            run_dir=run_dir,
            domain=domain,
            source_type=source_type,
            skill=skill,
            artifact_id=str(artifact.get("source_id") or ""),
            source_fetched_at=str(artifact.get("fetched_at") or artifact.get("source_fetched_at") or ""),
            topic_input=str(
                artifact_extra.get("topic")
                or artifact_extra.get("query")
                or extra.get("topic")
                or extra.get("query")
                or ""
            ),
        )

        extra = {**extra, "skill_id": skill["id"], "skill_rel_dir": skill["rel_dir"]}
        queue.update_item_fields(int(item["id"]), extra=extra, trace_id=str(skill["rel_dir"]))
        if verbose:
            print(f"[{utc_now_iso_z()}] SKILL  id={skill['id']} dir={skill['rel_dir']}", flush=True)
        queue.complete_attempt(int(item["id"]), status="ok")
        queue.requeue(int(item["id"]), new_stage="validate")
        return

    if stage == "validate":
        run_dir = _ensure_run_dir(repo_root, item, queue)
        root = run_dir / "skills"
        skill_rel_dir = str(extra.get("skill_rel_dir") or "").strip()
        if skill_rel_dir:
            cand = (run_dir / skill_rel_dir).resolve()
            if cand.exists():
                root = cand
        item_id = int(item.get("id") or 0)
        run_id = str(item.get("run_id") or run_dir.name).strip() or run_dir.name
        kind = str(extra.get("github_kind") or "").strip().lower()
        is_github_blob_budgeted = (
            source_type == "github"
            and int(settings.github_repo_fanout_n or 0) > 0
            and bool(run_id)
            and item_id > 0
            and kind == "blob"
        )

        if validate_skills is not None:
            try:
                errors, warnings = validate_skills(repo_root=repo_root, strict=bool(strict), root=root, check_package=True)
            except Exception:
                if is_github_blob_budgeted:
                    try:
                        queue.release_run_budget_reservation(run_id=run_id, budget_key="github_repo_skills", item_id=item_id)
                    except Exception:
                        pass
                raise
        else:
            errors, warnings = [], []
        for w in warnings:
            print(f"WARN: {w}")
        for e in errors:
            print(f"FAIL: {e}")
        if errors:
            if is_github_blob_budgeted:
                try:
                    queue.release_run_budget_reservation(run_id=run_id, budget_key="github_repo_skills", item_id=item_id)
                except Exception:
                    pass
            raise RuntimeError("validate_failed")

        if is_github_blob_budgeted:
            commit = queue.commit_run_budget(
                run_id=run_id,
                budget_key="github_repo_skills",
                item_id=item_id,
                target=int(settings.github_repo_fanout_n),
            )
            extra = {**extra, "budget_commit": commit}
            queue.update_item_fields(item_id, extra=extra)
        if settings.enable_improve_stage:
            queue.complete_attempt(int(item["id"]), status="ok")
            queue.requeue(int(item["id"]), new_stage="improve")
        elif settings.enable_publish_stage:
            queue.complete_attempt(int(item["id"]), status="ok")
            queue.requeue(int(item["id"]), new_stage="publish")
        else:
            queue.ack(int(item["id"]))
        return

    if stage == "improve":
        if not settings.enable_improve_stage:
            queue.complete_attempt(int(item["id"]), status="skip", error="improve_disabled")
            queue.requeue(int(item["id"]), new_stage="publish")
            return
        from ..skills.improve import improve_run_in_place

        run_dir = _ensure_run_dir(repo_root, item, queue)
        improve_run_in_place(repo_root=repo_root, run_target=str(run_dir), llm=llm, max_passes=3)
        if settings.enable_publish_stage:
            queue.complete_attempt(int(item["id"]), status="ok")
            queue.requeue(int(item["id"]), new_stage="publish")
        else:
            queue.ack(int(item["id"]))
        return

    if stage == "publish":
        if settings.enable_publish_stage:
            run_dir = _ensure_run_dir(repo_root, item, queue)
            publish_run_to_skills_library(repo_root=repo_root, run_dir=run_dir, overwrite=publish_overwrite)
        queue.ack(int(item["id"]))
        return

    if stage in {"done", "dead"}:
        return

    raise RuntimeError(f"Unknown stage: {stage}")


def _process_queue(
    *,
    repo_root: Path,
    queue: QueueStore,
    llm,
    max_tasks: int,
    rate_ms: int,
    publish_overwrite: bool,
    strict: bool,
    settings: QueueSettings,
    worker_id: str,
    verbose: bool,
    source_types: set[str] | None = None,
    max_stage: str | None = None,
    ignore_license_policy: bool = False,
) -> int:
    processed_count = 0
    stages = list(STAGE_ORDER)
    if max_stage:
        ms = str(max_stage or "").strip().lower()
        if ms and ms in stages:
            stages = stages[: stages.index(ms) + 1]

    while processed_count < max_tasks:
        made_progress = False
        for stage in stages:
            if processed_count >= max_tasks:
                break
            remaining = max_tasks - processed_count
            limit = min(remaining, settings.concurrency_global)
            if stage == "llm_generate":
                limit = min(limit, settings.llm_max_concurrency)
            if limit <= 0:
                continue

            items: list[dict[str, Any]] = []
            want_types = {str(x).strip().lower() for x in (source_types or set()) if str(x).strip()}
            if want_types:
                if settings.concurrency_per_source_type:
                    for stype, lim in settings.concurrency_per_source_type.items():
                        if len(items) >= limit:
                            break
                        st = str(stype or "").strip().lower()
                        if not st or st not in want_types:
                            continue
                        take = min(int(lim or 0), limit - len(items))
                        if take <= 0:
                            continue
                        items.extend(
                            queue.lease_next(
                                worker_id=worker_id,
                                limit=take,
                                stages=[stage],
                                source_type=st,
                                lease_seconds=settings.lease_seconds,
                            )
                        )
                remaining2 = limit - len(items)
                if remaining2 > 0 and want_types:
                    # Fill remaining capacity from the allowed types only (no fallback to other source types).
                    active = sorted(want_types)
                    while remaining2 > 0 and active:
                        progressed = False
                        for st in list(active):
                            if remaining2 <= 0:
                                break
                            more = queue.lease_next(
                                worker_id=worker_id,
                                limit=1 if len(active) > 1 else remaining2,
                                stages=[stage],
                                source_type=st,
                                lease_seconds=settings.lease_seconds,
                            )
                            if more:
                                items.extend(more)
                                remaining2 -= len(more)
                                progressed = True
                            else:
                                active.remove(st)
                        if not progressed:
                            break
            else:
                if settings.concurrency_per_source_type:
                    for stype, lim in settings.concurrency_per_source_type.items():
                        if len(items) >= limit:
                            break
                        take = min(lim, limit - len(items))
                        if take <= 0:
                            continue
                        items.extend(
                            queue.lease_next(
                                worker_id=worker_id,
                                limit=take,
                                stages=[stage],
                                source_type=stype,
                                lease_seconds=settings.lease_seconds,
                            )
                        )
                if len(items) < limit:
                    more = queue.lease_next(
                        worker_id=worker_id,
                        limit=limit - len(items),
                        stages=[stage],
                        lease_seconds=settings.lease_seconds,
                    )
                    items.extend(more)

            if not items:
                continue
            made_progress = True

            if stage == "ingest":
                forum_items = [it for it in items if str(it.get("source_type") or "").strip().lower() == "forum"]
                if forum_items:
                    _process_forum_ingest_batch(
                        repo_root=repo_root,
                        queue=queue,
                        items=forum_items,
                        settings=settings,
                        rate_ms=rate_ms,
                        verbose=verbose,
                    )
                    processed_count += len(forum_items)
                items = [it for it in items if str(it.get("source_type") or "").strip().lower() != "forum"]
                if not items:
                    continue

            def _run_one(item: dict[str, Any]) -> None:
                item_id = int(item.get("id") or 0)
                item_stage = str(item.get("stage") or stage)
                item_type = str(item.get("source_type") or "")
                item_url = str(item.get("source_url") or "")
                t0 = time.time()
                if verbose:
                    print(
                        f"[{utc_now_iso_z()}] START stage={item_stage} id={item_id} type={item_type} url={item_url}",
                        flush=True,
                    )
                try:
                    _process_item(
                        repo_root=repo_root,
                        item=item,
                        queue=queue,
                        llm=llm,
                        publish_overwrite=publish_overwrite,
                        strict=strict,
                        settings=settings,
                        ignore_license_policy=ignore_license_policy,
                        worker_id=worker_id,
                        verbose=verbose,
                    )
                    if verbose:
                        dt_ms = int((time.time() - t0) * 1000)
                        print(f"[{utc_now_iso_z()}] OK    stage={item_stage} id={item_id} ms={dt_ms}", flush=True)
                except Exception as e:
                    msg = str(e)
                    if isinstance(e, GitHubRateLimitError):
                        delay_s = max(1, int(getattr(e, "wait_seconds", 0) or 0))
                        delay_s = min(delay_s, 12 * 3600)
                        now_dt = _dt.datetime.now(tz=_dt.timezone.utc)
                        avail = utc_iso_z(now_dt + _dt.timedelta(seconds=delay_s))
                        queue.complete_attempt(item_id, status="wait", error="github_rate_limited")
                        queue.requeue(item_id, new_stage=item_stage)
                        queue.update_item_fields(item_id, available_at=avail, last_error=msg, last_error_at=utc_now_iso_z())
                        dt_ms = int((time.time() - t0) * 1000)
                        if verbose:
                            print(
                                f"[{utc_now_iso_z()}] WAIT  stage={item_stage} id={item_id} ms={dt_ms} backoff_s={delay_s} err={msg}",
                                flush=True,
                            )
                        return
                    attempts = int(item.get("attempts") or 0)
                    backoff = _compute_backoff_seconds(attempts, settings.backoff_base_seconds, settings.backoff_max_seconds)
                    outcome = queue.nack(int(item["id"]), reason=msg, backoff_seconds=backoff, max_attempts=None).get("status")
                    dt_ms = int((time.time() - t0) * 1000)
                    if str(outcome or "") == "dead":
                        if verbose:
                            print(f"[{utc_now_iso_z()}] DEAD  stage={item_stage} id={item_id} ms={dt_ms} err={msg}", flush=True)
                        else:
                            print(f"ERROR: {item_type} {item_url}: {msg}", flush=True)
                    elif verbose:
                        print(
                            f"[{utc_now_iso_z()}] REQUEUE stage={item_stage} id={item_id} ms={dt_ms} backoff_s={backoff} err={msg}",
                            flush=True,
                        )

                if stage == "llm_generate" and settings.llm_rate_limit_rps > 0:
                    time.sleep(max(0.0, 1.0 / float(settings.llm_rate_limit_rps)))
                if rate_ms and rate_ms > 0:
                    time.sleep(max(0.0, float(rate_ms) / 1000.0))

            max_workers = min(limit, len(items))
            use_threads = max_workers > 1 and stage != "llm_generate" and stage != "publish"
            if use_threads:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futs = [ex.submit(_run_one, item) for item in items]
                    for fut in as_completed(futs):
                        try:
                            fut.result()
                        except Exception as e:  # pragma: no cover - defensive
                            print(f"ERROR: worker crashed: {e}", flush=True)
                        processed_count += 1
            else:
                for item in items:
                    if processed_count >= max_tasks:
                        break
                    _run_one(item)
                    processed_count += 1

        if not made_progress:
            break

    return processed_count


def _migrate_state_json(state_path: Path, queue: QueueStore, settings: QueueSettings) -> int:
    if not state_path.exists():
        return 0
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    tasks = data.get("queue") if isinstance(data.get("queue"), list) else []
    migrated = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "").strip().lower()
        if status not in {"queued", "running"}:
            continue
        url = str(task.get("url") or "").strip()
        stype = str(task.get("source_type") or "").strip().lower()
        source_id = str(task.get("source_id") or "").strip() or sha256_hex(url)
        extra = dict(task.get("extra") if isinstance(task.get("extra"), dict) else {})
        queue.enqueue(
            source_id=source_id,
            source_type=stype or "webpage",
            source_url=url,
            source_title=str(task.get("title") or ""),
            stage="ingest",
            priority=0,
            max_attempts=settings.max_attempts,
            domain=str(task.get("domain") or ""),
            tags=extra.get("tags") if isinstance(extra.get("tags"), list) else [],
            config_snapshot=extra.get("config_snapshot") if isinstance(extra.get("config_snapshot"), dict) else {},
            extra=extra,
        )
        migrated += 1
    return migrated


def cli_runner(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai runner")
    parser.add_argument("--state", default="runs/queue.db", help="Legacy: queue DB path (or old runner_state.json)")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-ms", type=int, default=60_000)
    parser.add_argument("--rate-ms", type=int, default=1_000)
    parser.add_argument("--task-timeout-ms", type=int, default=600_000)
    parser.add_argument("--max-tasks", type=int, default=50)
    parser.add_argument("--max-attempts", type=int, default=0)
    parser.add_argument("--domain", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--topic", default="")
    parser.add_argument("--topics-file", default="", help="Optional topics yaml/json list to enqueue")
    parser.add_argument("--topics-limit", type=int, default=0)
    parser.add_argument("--publish-overwrite", dest="publish_overwrite", action="store_true")
    parser.add_argument("--publish-force", dest="publish_overwrite", action="store_true", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-discover", action="store_true", help="Skip discovery; only process existing queued items")
    parser.add_argument(
        "--discover-providers",
        default="web,github,forum",
        help="Comma-separated: web,github,forum (controls discovery only; does not affect existing queue items)",
    )
    parser.add_argument(
        "--ignore-license-policy",
        action="store_true",
        help="Do not skip/deny items based on license policy during discovery/ingest (still recorded in artifacts)",
    )
    parser.add_argument(
        "--enforce-license-policy",
        action="store_true",
        help="Enforce license policy during discovery/ingest (overrides --ignore-license-policy and the --no-llm default)",
    )
    parser.add_argument(
        "--max-stage",
        default="",
        help="Only process queue items up to this stage (inclusive): discover|ingest|preprocess|llm_generate|validate|improve|publish",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM-dependent stages (equivalent to --max-stage preprocess); useful when OPENAI/OLLAMA env is not set yet.",
    )
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--verbose", action="store_true", help="Print per-item progress logs")
    parser.add_argument(
        "--source-type",
        default="",
        help="Only process queue items with this source_type (comma-separated), e.g. github|webpage|forum",
    )
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root)
    max_stage = str(ns.max_stage or "").strip().lower()
    if bool(ns.no_llm):
        max_stage = "preprocess"

    llm = None
    if max_stage and max_stage not in STAGE_ORDER:
        raise RuntimeError(f"Invalid --max-stage: {max_stage} (expected one of: {', '.join(STAGE_ORDER)})")

    need_llm = (not max_stage) or (STAGE_ORDER.index(max_stage) >= STAGE_ORDER.index("llm_generate"))
    if need_llm:
        llm = create_llm_from_env(provider_override=None)
    offline = str(os.environ.get("LANGSKILLS_OFFLINE") or "").strip() == "1"
    if offline:
        raise RuntimeError("Offline mode is disabled; remove LANGSKILLS_OFFLINE.")

    settings = QueueSettings.from_env(repo_root_path=repo_root)
    if ns.queue:
        settings.path = Path(ns.queue)
    elif ns.state:
        settings.path = Path(ns.state)

    if not settings.path.is_absolute():
        settings.path = (repo_root / settings.path).resolve()

    queue = QueueStore(settings.path)
    queue.init_db()

    state_path = Path(ns.state) if ns.state else settings.path
    if not state_path.is_absolute():
        state_path = (repo_root / state_path).resolve()
    if state_path.suffix.lower() == ".json":
        migrated = _migrate_state_json(state_path, queue, settings)
        if migrated:
            print(f"Migrated {migrated} legacy queue items into {settings.path}")

    if str(os.environ.get("QUEUE_DRAIN") or "").strip() == "1":
        queue.set_meta("drain", "1")

    all_names = sorted(DOMAIN_CONFIG.keys())
    domains = _collect_domains(all_domains=bool(ns.all), domain=ns.domain or None)
    topic_override = str(ns.topic or "").strip() or None
    topics_batch: list[dict[str, Any]] = []
    if ns.topics_file:
        topics_path = Path(ns.topics_file)
        if not topics_path.is_absolute():
            topics_path = repo_root / topics_path
        if topics_path.exists():
            try:
                if topics_path.suffix.lower() == ".json":
                    data = json.loads(topics_path.read_text(encoding="utf-8"))
                else:
                    from ..utils.yaml_lite import safe_load_yaml_text

                    data = safe_load_yaml_text(topics_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data = data.get("topics") or []
                if isinstance(data, list):
                    out: list[dict[str, Any]] = []
                    for t in data:
                        if isinstance(t, dict):
                            topic_str = str(t.get("topic") or "").strip()
                            tags = t.get("tags") if isinstance(t.get("tags"), list) else []
                            profile = str(t.get("profile") or t.get("domain") or "").strip()
                        else:
                            topic_str = str(t).strip()
                            tags = []
                            profile = ""
                        if not topic_str:
                            continue
                        out.append({"topic": topic_str, "tags": tags, "profile": profile})
                    topics_batch = out
            except Exception:
                topics_batch = []
        if ns.topics_limit and ns.topics_limit > 0:
            topics_batch = topics_batch[: ns.topics_limit]

    max_attempts = int(ns.max_attempts or settings.max_attempts)
    worker_id = str(ns.worker_id or "").strip() or f"worker-{os.getpid()}"
    ignore_license_policy = bool(ns.ignore_license_policy) or bool(ns.no_llm)
    if bool(ns.enforce_license_policy):
        ignore_license_policy = False
    verbose = bool(ns.verbose) or str(os.environ.get("LANGSKILLS_RUNNER_VERBOSE") or "").strip() == "1"
    source_types = {x.strip().lower() for x in str(ns.source_type or "").split(",") if x.strip()}

    def _parse_discover_providers(raw: str) -> set[str]:
        s = str(raw or "").strip()
        if not s:
            return set()
        out: set[str] = set()
        for chunk in s.split(","):
            name = chunk.strip().lower()
            if not name:
                continue
            if name in {"web", "webpage", "page"}:
                out.add("webpage")
            elif name in {"github", "gh"}:
                out.add("github")
            elif name in {"forum", "forums", "so", "stackoverflow", "stack"}:
                out.add("forum")
            else:
                raise RuntimeError(f"Unknown discover provider: {name}")
        return out

    discover_providers = _parse_discover_providers(ns.discover_providers)

    while True:
        draining = bool(queue.is_draining())
        print(
            f"[{utc_now_iso_z()}] Cycle start: queue={settings.path} max_tasks={ns.max_tasks} max_stage={max_stage or 'full'} no_discover={bool(ns.no_discover)} drain={1 if draining else 0} source_type={','.join(sorted(source_types)) if source_types else 'all'}",
            flush=True,
        )
        queue.gc(reclaim_expired=True)
        if draining and not bool(ns.no_discover) and discover_providers:
            print(
                f"[{utc_now_iso_z()}] WARN: queue drain is enabled; discovery enqueues are suppressed (unset QUEUE_DRAIN or clear queue_meta.drain).",
                flush=True,
            )

        if not bool(ns.no_discover) and discover_providers and not draining:
            if topics_batch:
                for entry in topics_batch:
                    topic_str = str(entry.get("topic") or "").strip()
                    if not topic_str:
                        continue
                    tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []
                    profile = str(entry.get("profile") or "").strip()
                    if profile and profile in all_names:
                        domains_for_topic = [profile]
                    elif not ns.domain and not ns.all:
                        if llm:
                            picked = classify_domain_by_llm(topic=topic_str, domains=all_names, llm=llm)
                        else:
                            picked = default_domain_for_topic(topic_str)
                        domains_for_topic = [picked]
                    else:
                        domains_for_topic = domains
                    _discover_tasks(
                        domains=domains_for_topic,
                        topic_override=topic_str,
                        topic_tags=tags,
                        queue=queue,
                        repo_root=repo_root,
                        max_attempts=max_attempts,
                        discover_providers=discover_providers,
                        ignore_license_policy=ignore_license_policy,
                        verbose=verbose,
                    )
            else:
                _discover_tasks(
                    domains=domains,
                    topic_override=topic_override,
                    topic_tags=[],
                    queue=queue,
                    repo_root=repo_root,
                    max_attempts=max_attempts,
                    discover_providers=discover_providers,
                    ignore_license_policy=ignore_license_policy,
                    verbose=verbose,
                )
        elif (topics_batch or topic_override) and bool(ns.no_discover):
            print("WARN: --no-discover is set; ignoring --topic/--topics-file for discovery.")

        processed = _process_queue(
            repo_root=repo_root,
            queue=queue,
            llm=llm,
            max_tasks=ns.max_tasks,
            rate_ms=ns.rate_ms,
            publish_overwrite=bool(ns.publish_overwrite),
            strict=bool(ns.strict),
            settings=settings,
            worker_id=worker_id,
            verbose=verbose,
            source_types=source_types or None,
            max_stage=max_stage or None,
            ignore_license_policy=ignore_license_policy,
        )
        print(f"Cycle processed: {processed}", flush=True)
        if processed == 0 and verbose and source_types:
            try:
                conn = queue._connect()  # type: ignore[attr-defined]
            except Exception:
                conn = None
            if conn is not None:
                try:
                    stypes = sorted(source_types)
                    placeholders = ",".join(["?"] * len(stypes))
                    rows = conn.execute(
                        f"""
                        SELECT stage, status, COUNT(*) AS c
                        FROM queue_items
                        WHERE source_type IN ({placeholders})
                        GROUP BY stage, status
                        ORDER BY stage, status
                        """,
                        stypes,
                    ).fetchall()
                    summary = " ".join([f"{r['stage']}/{r['status']}={int(r['c'] or 0)}" for r in rows]) if rows else "none"
                    print(f"[{utc_now_iso_z()}] INFO: filtered queue counts: {summary}", flush=True)
                    if max_stage:
                        try:
                            max_stage_idx = STAGE_ORDER.index(max_stage)
                        except Exception:
                            max_stage_idx = -1
                        if max_stage_idx >= 0 and rows:
                            queued_stage_idxs: list[int] = []
                            for r in rows:
                                if str(r["status"] or "").strip().lower() != "queued":
                                    continue
                                st = str(r["stage"] or "").strip().lower()
                                if st not in STAGE_ORDER:
                                    continue
                                queued_stage_idxs.append(STAGE_ORDER.index(st))
                            if queued_stage_idxs and min(queued_stage_idxs) > max_stage_idx:
                                next_stage = STAGE_ORDER[min(queued_stage_idxs)]
                                print(
                                    f"[{utc_now_iso_z()}] INFO: no items eligible under max_stage={max_stage}; "
                                    f"queued items start at stage={next_stage} (remove --no-llm or run with a configured LLM).",
                                    flush=True,
                                )
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

        if ns.once:
            break
        time.sleep(max(1.0, float(ns.interval_ms) / 1000.0))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_runner())
