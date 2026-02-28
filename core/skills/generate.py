from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import (
    DOMAIN_CONFIG,
    canonicalize_source_url,
    compute_method_counts,
    default_domain_for_topic,
    get_crawl_policy_from_config,
    is_url_allowed_by_host_policy,
    license_decision,
    read_license_policy,
)
from ..env import load_dotenv
from ..llm.factory import create_llm_from_env
from ..llm.types import ChatMessage, LlmClient
from ..sources.artifacts import write_source_artifact
from ..sources.github import GithubRepo, combine_repo_text, github_fetch_readme_excerpt_raw, github_search_top_repos
from ..sources.stackoverflow import (
    StackQuestion,
    combine_question_answer_text,
    pick_answer_for_question,
    stack_fetch_answers_with_body,
    stack_fetch_questions_with_body,
    stack_search_top_questions,
)
from ..sources.arxiv import discover_arxiv_sources, search_arxiv
from ..sources.types import SourceInput
from ..sources.router import fetch_text
from ..sources.web_search import search_web_urls
from ..utils.fs import ensure_dir, make_run_dir, rmrf, write_json_atomic, write_text_atomic
from ..utils.hashing import sha256_hex, slugify
from ..utils.md import lint_skill_markdown
from ..utils.redact import redact_obj
from ..utils.time import utc_now_iso_z
from ..utils.text import truncate_text
from ..utils.yaml_simple import write_metadata_yaml_text
from ..utils.lang import resolve_output_language
from .coerce import coerce_markdown, coerce_string
from .gate import run_skill_gate
from .markdown_ops import (
    ensure_at_least_one_code_block,
    ensure_evidence_section,
    ensure_sources_contain_url,
    ensure_triad_sections,
    ensure_verification_has_code_block,
    strip_raw_urls_outside_sources,
)
from .package_v2 import build_skill_package_v2_with_llm
from .prompts import make_domain_router_prompt, make_skill_prompt


@dataclass(frozen=True)
class SkillId:
    id: str
    topic: str
    slug: str


def make_skill_id(*, domain: str, method: str, seq: int, base_slug: str) -> SkillId:
    topic = str(method or "").strip()
    seq_part = str(int(seq)).rjust(4, "0")
    slug_part = slugify(base_slug, 40)
    slug = f"{(topic[:1] or 'x')}-{seq_part}-{slug_part}"
    skill_id = f"{domain}/{topic}/{slug}"
    return SkillId(id=skill_id, topic=topic, slug=slug)


def _write_metadata_yaml(path: str | Path, meta: dict[str, Any]) -> None:
    write_text_atomic(path, write_metadata_yaml_text(meta))


def _prompt_sha(messages: list[ChatMessage]) -> str:
    payload = [m.to_dict() for m in messages]
    return sha256_hex(json.dumps(payload, ensure_ascii=False))


def classify_domain_by_llm(*, topic: str, domains: list[str], llm: LlmClient) -> str:
    allowed = [d for d in (domains or []) if str(d or "").strip()]
    if not allowed:
        return default_domain_for_topic(topic)
    if not llm:
        raise RuntimeError("LLM client required for domain classification.")

    messages = make_domain_router_prompt(topic=topic, allowed_domains=allowed)
    out = llm.chat_json(messages=messages, temperature=0.0, timeout_ms=30_000)
    picked = str(out.get("domain") or "").strip()
    return picked if picked in allowed else default_domain_for_topic(topic)


def generate_one_skill(
    *,
    run_dir: str | Path,
    domain: str,
    method: str,
    seq: int,
    base_slug: str,
    source: SourceInput,
    llm: LlmClient,
) -> dict[str, Any]:
    sid = make_skill_id(domain=domain, method=method, seq=seq, base_slug=base_slug)
    skill_dir = Path(run_dir) / "skills" / domain / sid.topic / sid.slug
    ensure_dir(skill_dir)

    source_url_raw = str(source.url or "").strip()
    source_url = canonicalize_source_url(source_url_raw) or source_url_raw
    source_title = str(source.title or "").strip()
    extracted_text = truncate_text(str(source.text or ""), 12_000)
    extra_context = dict(source.extra or {})
    skill_kind = str(extra_context.get("skill_kind") or "").strip()
    language = resolve_output_language(default="en")
    extra_context["language"] = language
    source_refs = extra_context.get("source_refs") if isinstance(extra_context.get("source_refs"), list) else []
    now_iso = utc_now_iso_z()
    source_fetched_at = str(source.fetched_at or extra_context.get("source_fetched_at") or "").strip()

    messages = make_skill_prompt(
        domain=domain,
        method=method,
        skill_id=sid.id,
        source_url=source_url,
        source_title=source_title,
        extracted_text=extracted_text,
        extra_context=extra_context,
        skill_kind=skill_kind,
    )
    prompt_sha = _prompt_sha(messages)

    out: dict[str, Any] | None = None
    last_err: Exception | None = None
    for attempt in range(0, 2):
        try:
            out = llm.chat_json(messages=messages, temperature=0.2 if attempt == 0 else 0.0, timeout_ms=300_000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))

    if not isinstance(out, dict):
        raise RuntimeError(f"LLM generation failed for {sid.id}") from last_err

    title = coerce_string(out.get("title")).strip() or sid.id
    skill_md = coerce_markdown(out.get("skill_md"))
    review = out.get("review") if isinstance(out.get("review"), dict) else {}

    md_ok = bool(skill_md.strip()) and len(skill_md.strip()) >= 50 and bool(re.match(r"^#\s+", skill_md.strip()))
    if not md_ok:
        raise RuntimeError(f"Invalid skill_md for {sid.id} (missing markdown title / too short)")

    skill_md = ensure_sources_contain_url(skill_md, source_url)
    run_id = Path(run_dir).name
    evidence_lines = [f"- run_id: {run_id}", f"- prompt_sha256: {prompt_sha}"]
    artifact_id = str(extra_context.get("source_artifact_id") or "").strip()
    if artifact_id:
        evidence_lines.append(f"- source_artifact: captures/{run_id}/sources/{artifact_id}.json")
        if not source_refs:
            source_refs = [{"source_id": artifact_id, "source_type": method, "source_url": source_url}]
    skill_md = ensure_evidence_section(skill_md, evidence_lines)
    skill_md = strip_raw_urls_outside_sources(skill_md)
    skill_md = ensure_at_least_one_code_block(skill_md)
    skill_md = ensure_verification_has_code_block(skill_md)
    if str(skill_kind or "").strip().lower() not in {"paper_writing", "paper_writeup", "experiment_design"}:
        skill_md = ensure_triad_sections(skill_md)
    lint_issues = lint_skill_markdown(skill_md)

    pkg = build_skill_package_v2_with_llm(
        llm=llm,
        domain=domain,
        method=method,
        skill_id=sid.id,
        title=title,
        source_url=source_url,
        source_fetched_at=source_fetched_at,
        package_generated_at=now_iso,
        license_spdx=str(extra_context.get("license_spdx") or ""),
        license_risk=str(extra_context.get("license_risk") or ""),
        skill_md=skill_md,
        source_excerpt=extracted_text,
    )

    meta_out: dict[str, Any] = {
        "id": sid.id,
        "title": title,
        "domain": domain,
        "topic": sid.topic,
        "slug": sid.slug,
        "source_type": method,
        "source_url": source_url,
        "source_fetched_at": source_fetched_at,
        "generated_at": now_iso,
        "llm_provider": getattr(llm, "provider", ""),
        "llm_model": getattr(llm, "model", ""),
        "prompt_sha256": prompt_sha,
        "overall_score": float(review.get("overall_score") or 0) if isinstance(review, dict) else 0,
        "source_artifact_id": str(extra_context.get("source_artifact_id") or ""),
        "primary_source_id": str(extra_context.get("source_artifact_id") or ""),
        "source_refs": source_refs,
        "license_spdx": str(extra_context.get("license_spdx") or ""),
        "license_risk": str(extra_context.get("license_risk") or ""),
        "package_schema_version": 2,
        "package_generated_at": now_iso,
        "package_llm_provider": getattr(llm, "provider", ""),
        "package_llm_model": getattr(llm, "model", ""),
        "skill_kind": skill_kind or sid.topic,
        "language": language,
        "profile": domain,
        "tags": extra_context.get("tags") if isinstance(extra_context.get("tags"), list) else [],
    }

    save_llm_raw = str(os.environ.get("LANGSKILLS_SAVE_LLM_ARTIFACTS") or "").strip()
    save_llm_artifacts = True if save_llm_raw == "" else (save_llm_raw != "0")
    if save_llm_artifacts:
        redact_urls = str(os.environ.get("LANGSKILLS_REDACT_URLS") or "").strip() == "1"
        write_json_atomic(
            skill_dir / "prompt.json",
            redact_obj(
                {
                    "created_at": utc_now_iso_z(),
                    "llm_provider": getattr(llm, "provider", ""),
                    "llm_model": getattr(llm, "model", ""),
                    "prompt_sha256": prompt_sha,
                    "messages": [m.to_dict() for m in messages],
                },
                redact_urls=redact_urls,
            ),
        )
        write_json_atomic(
            skill_dir / "response.json",
            redact_obj(
                {
                    "created_at": utc_now_iso_z(),
                    "llm_provider": getattr(llm, "provider", ""),
                    "llm_model": getattr(llm, "model", ""),
                    "output": out,
                },
                redact_urls=redact_urls,
            ),
        )

    write_text_atomic(skill_dir / "skill.md", skill_md)
    write_text_atomic(skill_dir / "library.md", pkg.library_md)
    ref_dir = skill_dir / "reference"
    ensure_dir(ref_dir)
    write_text_atomic(ref_dir / "sources.md", pkg.reference["sources_md"])
    write_text_atomic(ref_dir / "troubleshooting.md", pkg.reference["troubleshooting_md"])
    write_text_atomic(ref_dir / "edge-cases.md", pkg.reference["edge_cases_md"])
    write_text_atomic(ref_dir / "examples.md", pkg.reference["examples_md"])
    write_text_atomic(ref_dir / "changelog.md", pkg.reference["changelog_md"])
    _write_metadata_yaml(skill_dir / "metadata.yaml", meta_out)

    return {
        "id": sid.id,
        "title": title,
        "domain": domain,
        "topic": sid.topic,
        "slug": sid.slug,
        "rel_dir": skill_dir.relative_to(Path(run_dir)).as_posix(),
        "source_type": method,
        "source_url": source_url,
        "review": review,
        "lint_issues": lint_issues,
    }


def generate_domain_batch(
    *,
    repo_root: str | Path,
    run_dir: str | Path,
    domain: str,
    config: dict[str, Any],
    topic: str,
    llm: LlmClient,
    counts: dict[str, int] | None,
    tags: list[str] | None,
    offline: bool,
    pretty: bool,
) -> dict[str, Any]:
    want = counts or compute_method_counts(config=config, total=None, per_source=None)
    want_web = max(0, int(want.get("web") or 0))
    want_gh = max(0, int(want.get("github") or 0))
    want_forum = max(0, int(want.get("forum") or 0))
    want_arxiv = max(0, int(want.get("arxiv") or 0))
    if want_arxiv == 0 and domain == "ml":
        want_arxiv = max(3, want_web // 3)

    if bool(offline) or str(os.environ.get("LANGSKILLS_OFFLINE") or "").strip() == "1":
        raise RuntimeError("Offline mode is disabled; remove LANGSKILLS_OFFLINE or --offline.")

    tag_list = [str(t).strip() for t in (tags or []) if str(t).strip()]
    results: dict[str, Any] = {
        "domain": domain,
        "topic_input": topic,
        "counts_requested": {"web": want_web, "github": want_gh, "forum": want_forum, "arxiv": want_arxiv},
        "web": [],
        "github": [],
        "forum": [],
        "arxiv": [],
        "web_errors": [],
        "github_errors": [],
        "forum_errors": [],
        "arxiv_errors": [],
    }

    def _canon(url: str) -> str:
        u = str(url or "").strip()
        if not u:
            return ""
        try:
            return canonicalize_source_url(u) or u
        except Exception:
            return u

    # 1) Web pages
    if want_web > 0:
        policy = get_crawl_policy_from_config(config, "webpage")
        web_buf = 5

        import sys as _sys
        print(f"[capture] {domain}/{topic}: searching web URLs (want={want_web})...", flush=True)
        search_urls = search_web_urls(topic, limit=want_web + web_buf)
        web_urls_all: list[str] = []
        for u in search_urls:
            s = str(u or "").strip()
            if not s or s in web_urls_all:
                continue
            web_urls_all.append(s)

        if not web_urls_all:
            seed_urls = config.get("web_urls") or []
            for u in seed_urls:
                s = str(u or "").strip()
                if s and s not in web_urls_all:
                    web_urls_all.append(s)

        candidates = web_urls_all[: min(len(web_urls_all), want_web + web_buf)]
        print(f"[capture] {domain}/{topic}: found {len(search_urls)} search + {len(web_urls_all)} total URLs, {len(candidates)} candidates", flush=True)

        if want_web > len(web_urls_all):
            results["web_errors"].append(f"Requested {want_web} web skills, but only {len(web_urls_all)} web URLs found.")

        web_ok: list[dict[str, Any]] = []
        for idx, url in enumerate(candidates, start=1):
            if len(web_ok) >= want_web:
                break
            url0 = _canon(url)
            if not is_url_allowed_by_host_policy(url0, policy):
                results["web_errors"].append(f"Blocked by crawl policy (webpage): {url0}")
                continue

            print(f"[capture] {domain}/{topic}: [{idx}/{len(candidates)}] fetch+gen {url0[:80]}...", flush=True)
            try:
                fetched = fetch_text(url0, engine="auto")
                raw_html = fetched.raw_html
                text = fetched.extracted_text

                src = write_source_artifact(
                    run_dir=run_dir,
                    source_type="webpage",
                    url=url0,
                    title="",
                    raw_text=raw_html,
                    extracted_text=text,
                    license_spdx="",
                    license_risk="unknown",
                    extra={"domain": domain, "topic": topic, **({"tags": tag_list} if tag_list else {})},
                )

                gate = run_skill_gate(
                    run_dir=run_dir,
                    domain=domain,
                    method="webpage",
                    source_id=src.source_id,
                    source_url=url0,
                    source_title="",
                    extracted_text=str(src.extracted_text or text),
                    llm=llm,
                )
                if not bool(gate.get("allow_generate")):
                    results["web_errors"].append(f"SkillGate skip (verdict={gate.get('verdict')}): {url0}")
                    continue

                out_skill = generate_one_skill(
                    run_dir=run_dir,
                    domain=domain,
                    method="webpage",
                    seq=idx,
                    base_slug=f"{domain}-web-{idx}",
                    source=SourceInput(
                        source_type="webpage",
                        url=url0,
                        title="",
                        text=str(src.extracted_text or text),
                        fetched_at=src.fetched_at,
                        extra={
                            "source_artifact_id": src.source_id,
                            "license_spdx": src.license_spdx,
                            "license_risk": src.license_risk,
                            **({"tags": tag_list} if tag_list else {}),
                        },
                    ),
                    llm=llm,
                )
                web_ok.append(out_skill)
                print(f"[capture] {domain}/{topic}: [{idx}/{len(candidates)}] OK skills={len(web_ok)}/{want_web}", flush=True)
            except Exception as e:
                print(f"[capture] {domain}/{topic}: [{idx}/{len(candidates)}] FAIL: {e}", flush=True)
                results["web_errors"].append(str(e))

        print(f"[capture] {domain}/{topic}: web done — {len(web_ok)} skills generated", flush=True)
        results["web"] = web_ok[:want_web]
        if not pretty:
            for extra in web_ok[want_web:]:
                rel_dir = str(extra.get("rel_dir") or "").strip()
                if rel_dir:
                    rmrf(Path(run_dir) / rel_dir)

        if len(results["web"]) < want_web:
            results["web_errors"].append(f"Generated {len(results['web'])}/{want_web} web skills.")

    # 2) GitHub repos
    if want_gh > 0:
        try:
            min_stars = int(config.get("github", {}).get("min_stars") or 0)
            pushed_after = str(config.get("github", {}).get("pushed_after") or "").strip()
            q = f"{topic}".strip()
            if pushed_after:
                q = f"{q} pushed:>{pushed_after}".strip()
            raw_repos: list[GithubRepo]
            gh_buf = 5
            raw_repos = github_search_top_repos(
                query=q,
                per_page=100,
                min_stars=min_stars,
                pushed_after=pushed_after or None,
            )

            host_policy = get_crawl_policy_from_config(config, "github")
            policy = read_license_policy(repo_root)

            repos: list[GithubRepo] = []
            for repo in raw_repos:
                url = _canon(str(repo.html_url or ""))
                if not url:
                    continue
                if not is_url_allowed_by_host_policy(url, host_policy):
                    results["github_errors"].append(f"Blocked by crawl policy (github): {url}")
                    continue

                spdx = str(repo.license_spdx or "").strip()
                if license_decision(policy, source_type="github", license_spdx=spdx) == "deny":
                    results["github_errors"].append(f"Skipped denied license repo ({spdx or 'unknown'}): {url}")
                    continue
                repos.append(repo)
                if len(repos) >= want_gh + gh_buf:
                    break

            gh_ok: list[dict[str, Any]] = []
            for idx, repo in enumerate(repos, start=1):
                if len(gh_ok) >= want_gh:
                    break
                readme = ""
                try:
                    readme = github_fetch_readme_excerpt_raw(full_name=repo.full_name, default_branch=repo.default_branch)
                except Exception:
                    readme = ""

                combined = combine_repo_text(repo, readme)
                src = write_source_artifact(
                    run_dir=run_dir,
                    source_type="github",
                    url=_canon(str(repo.html_url or "")),
                    title=repo.full_name,
                    raw_text=combined,
                    extracted_text=combined,
                    license_spdx=str(repo.license_spdx or "").strip(),
                    license_risk="unknown",
                    extra={
                        "domain": domain,
                        "topic": topic,
                        "repo": repo.full_name,
                        "stars": repo.stargazers_count,
                        "language": repo.language,
                        **({"tags": tag_list} if tag_list else {}),
                    },
                )

                gate = run_skill_gate(
                    run_dir=run_dir,
                    domain=domain,
                    method="github",
                    source_id=src.source_id,
                    source_url=_canon(str(repo.html_url or "")),
                    source_title=repo.full_name,
                    extracted_text=combined,
                    llm=llm,
                )
                if not bool(gate.get("allow_generate")):
                    results["github_errors"].append(
                        f"SkillGate skip (verdict={gate.get('verdict')}): {_canon(str(repo.html_url or ''))}"
                    )
                    continue

                out_skill = generate_one_skill(
                    run_dir=run_dir,
                    domain=domain,
                    method="github",
                    seq=idx,
                    base_slug=repo.full_name,
                    source=SourceInput(
                        source_type="github",
                        url=_canon(str(repo.html_url or "")),
                        title=repo.full_name,
                        text=combined,
                        fetched_at=src.fetched_at,
                        extra={
                            "repo": repo.full_name,
                            "stars": repo.stargazers_count,
                            "language": repo.language,
                            "source_artifact_id": src.source_id,
                            "license_spdx": src.license_spdx,
                            "license_risk": src.license_risk,
                            **({"tags": tag_list} if tag_list else {}),
                        },
                    ),
                    llm=llm,
                )
                gh_ok.append(out_skill)

            results["github"] = gh_ok[:want_gh]
            if not pretty:
                for extra in gh_ok[want_gh:]:
                    rel_dir = str(extra.get("rel_dir") or "").strip()
                    if rel_dir:
                        rmrf(Path(run_dir) / rel_dir)

            if len(results["github"]) < want_gh:
                results["github_errors"].append(f"Generated {len(results['github'])}/{want_gh} GitHub skills.")
        except Exception as e:
            results["github_errors"].append(str(e))
            results["github_errors"].append(f"Generated 0/{want_gh} GitHub skills.")

    # 3) Forum (StackOverflow)
    if want_forum > 0:
        try:
            forum_q = str(topic or "").strip()
            forum_buf = 5
            forum_tagged = str(config.get("forum", {}).get("tagged") or "").strip() or None
            top_qs = stack_search_top_questions(
                q=forum_q,
                tagged=forum_tagged,
                pagesize=min(100, want_forum + forum_buf),
            )
            if not top_qs and forum_tagged:
                top_qs = stack_search_top_questions(
                    q=forum_q,
                    tagged=None,
                    pagesize=min(100, want_forum + forum_buf),
                )

            forum_policy = get_crawl_policy_from_config(config, "forum")
            top_qs = [q for q in top_qs if q.link and is_url_allowed_by_host_policy(_canon(q.link), forum_policy)]
            ids = [q.question_id for q in top_qs if q.question_id]
            questions = stack_fetch_questions_with_body(question_ids=ids)
            answers = stack_fetch_answers_with_body(question_ids=ids)

            question_by_id = {q.question_id: q for q in questions}
            ordered_questions = [question_by_id.get(q.question_id) for q in top_qs]
            ordered_questions = [q for q in ordered_questions if q]

            forum_ok: list[dict[str, Any]] = []
            for idx, q in enumerate(ordered_questions, start=1):
                if len(forum_ok) >= want_forum:
                    break

                ans = pick_answer_for_question(q, answers)

                combined = combine_question_answer_text(q, ans)
                link = _canon(q.link)
                src = write_source_artifact(
                    run_dir=run_dir,
                    source_type="forum",
                    url=link,
                    title=q.title,
                    raw_text=combined,
                    extracted_text=combined,
                    license_spdx="CC-BY-SA-4.0",
                    license_risk="attribution_required",
                    extra={
                        "domain": domain,
                        "topic": topic,
                        "stackoverflow_question_id": q.question_id,
                        "accepted_answer_id": q.accepted_answer_id,
                        **({"tags": tag_list} if tag_list else {}),
                    },
                )

                gate = run_skill_gate(
                    run_dir=run_dir,
                    domain=domain,
                    method="forum",
                    source_id=src.source_id,
                    source_url=link,
                    source_title=q.title,
                    extracted_text=combined,
                    llm=llm,
                )
                if not bool(gate.get("allow_generate")):
                    results["forum_errors"].append(f"SkillGate skip (verdict={gate.get('verdict')}): {link}")
                    continue

                out_skill = generate_one_skill(
                    run_dir=run_dir,
                    domain=domain,
                    method="forum",
                    seq=idx,
                    base_slug=f"so-{q.question_id}-{q.title}",
                    source=SourceInput(
                        source_type="forum",
                        url=link,
                        title=q.title,
                        text=combined,
                        fetched_at=src.fetched_at,
                        extra={
                            "stackoverflow_question_id": q.question_id,
                            "accepted_answer_id": q.accepted_answer_id,
                            "source_artifact_id": src.source_id,
                            "license_spdx": src.license_spdx,
                            "license_risk": src.license_risk,
                            **({"tags": tag_list} if tag_list else {}),
                        },
                    ),
                    llm=llm,
                )
                forum_ok.append(out_skill)

            results["forum"] = forum_ok[:want_forum]
            if not pretty:
                for extra in forum_ok[want_forum:]:
                    rel_dir = str(extra.get("rel_dir") or "").strip()
                    if rel_dir:
                        rmrf(Path(run_dir) / rel_dir)

            if len(results["forum"]) < want_forum:
                results["forum_errors"].append(f"Generated {len(results['forum'])}/{want_forum} forum skills.")
        except Exception as e:
            results["forum_errors"].append(str(e))
            results["forum_errors"].append(f"Generated 0/{want_forum} forum skills.")

    # 4) ArXiv papers (primarily for ML domain)
    if want_arxiv > 0:
        try:
            arxiv_entries = search_arxiv(topic, max_results=want_arxiv + 5)
            arxiv_ok: list[dict[str, Any]] = []
            for idx, entry in enumerate(arxiv_entries, start=1):
                if len(arxiv_ok) >= want_arxiv:
                    break
                src_input = discover_arxiv_sources(topic, max_results=1, skill_kinds=["paper_writing"])
                if not src_input:
                    continue

                url_raw = entry.get("primary_url") or ""
                url0 = _canon(url_raw)
                if not url0:
                    continue

                abstract = entry.get("summary") or ""
                comment = str(entry.get("comment") or "").strip()
                comment_block = f"\n\nCOMMENT:\n{comment}" if comment else ""
                text = (
                    f"TITLE: {entry.get('title', '')}\n"
                    f"AUTHORS: {', '.join(entry.get('authors') or [])}\n\n"
                    f"ABSTRACT:\n{abstract}{comment_block}"
                )

                src = write_source_artifact(
                    run_dir=run_dir,
                    source_type="arxiv",
                    url=url0,
                    title=entry.get("title") or "",
                    raw_text=text,
                    extracted_text=text,
                    license_spdx="arxiv-perpetual",
                    license_risk="low",
                    extra={
                        "domain": domain,
                        "topic": topic,
                        "arxiv_id": entry.get("arxiv_id") or "",
                        "pdf_url": entry.get("pdf_url") or "",
                        "authors": entry.get("authors") or [],
                        **({"tags": tag_list} if tag_list else {}),
                    },
                )

                gate = run_skill_gate(
                    run_dir=run_dir,
                    domain=domain,
                    method="arxiv",
                    source_id=src.source_id,
                    source_url=url0,
                    source_title=entry.get("title") or "",
                    extracted_text=text,
                    llm=llm,
                )
                if not bool(gate.get("allow_generate")):
                    results["arxiv_errors"].append(
                        f"SkillGate skip (verdict={gate.get('verdict')}): {url0}"
                    )
                    continue

                out_skill = generate_one_skill(
                    run_dir=run_dir,
                    domain=domain,
                    method="arxiv",
                    seq=idx,
                    base_slug=entry.get("title") or f"arxiv-{entry.get('arxiv_id', '')}",
                    source=SourceInput(
                        source_type="arxiv",
                        url=url0,
                        title=entry.get("title") or "",
                        text=text,
                        fetched_at=src.fetched_at,
                        extra={
                            "arxiv_id": entry.get("arxiv_id") or "",
                            "pdf_url": entry.get("pdf_url") or "",
                            "authors": entry.get("authors") or [],
                            "source_artifact_id": src.source_id,
                            "license_spdx": "arxiv-perpetual",
                            "license_risk": "low",
                            **({"tags": tag_list} if tag_list else {}),
                        },
                    ),
                    llm=llm,
                )
                arxiv_ok.append(out_skill)

            results["arxiv"] = arxiv_ok[:want_arxiv]
            if len(results["arxiv"]) < want_arxiv:
                results["arxiv_errors"].append(f"Generated {len(results['arxiv'])}/{want_arxiv} ArXiv skills.")
        except Exception as e:
            results["arxiv_errors"].append(str(e))
            results["arxiv_errors"].append(f"Generated 0/{want_arxiv} ArXiv skills.")

    return results


def render_quality_report(*, run_dir: str | Path, run_manifest: dict[str, Any]) -> None:
    m = dict(run_manifest or {})
    domains = m.get("domains") if isinstance(m.get("domains"), list) else []

    lines: list[str] = []
    lines.append("# Skill Generation Quality Report")
    lines.append("")
    lines.append(f"- Run: {m.get('run_id', '')}")
    lines.append(f"- Topic input: {m.get('topic_input', '')}")
    lines.append(f"- Generated at: {m.get('generated_at', '')}")
    lines.append("")

    def flatten(domain_entry: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for k in ("web", "github", "forum", "arxiv"):
            arr = domain_entry.get(k) if isinstance(domain_entry.get(k), list) else []
            for s in arr:
                if isinstance(s, dict):
                    out.append({"method": k, **s})
        return out

    def score(review: Any) -> float:
        if not isinstance(review, dict):
            return 0.0
        try:
            n = float(review.get("overall_score") or 0)
        except Exception:
            return 0.0
        return max(0.0, min(5.0, n))

    total = 0
    score_sum = 0.0
    lint_total = 0
    for d in domains:
        if not isinstance(d, dict):
            continue
        for s in flatten(d):
            total += 1
            score_sum += score(s.get("review"))
            lint = s.get("lint_issues") if isinstance(s.get("lint_issues"), list) else []
            lint_total += len(lint)

    avg = f"{(score_sum / total):.2f}" if total else "0.00"
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total skills: {total}")
    lines.append(f"- Avg LLM score (1-5): {avg}")
    lines.append(f"- Total linter issues: {lint_total}")
    lines.append("")

    for d in domains:
        if not isinstance(d, dict):
            continue
        lines.append(f"## Domain: {d.get('domain', '')}")
        lines.append("")
        for s in flatten(d):
            lines.append(f"### {s.get('id', '')}")
            lines.append("")
            lines.append(f"- Title: {s.get('title', '')}")
            lines.append(f"- Method: {s.get('source_type') or s.get('method')}")
            lines.append(f"- Source: {s.get('source_url', '')}")
            lines.append(f"- Output: {s.get('rel_dir', '')}")
            lines.append(f"- Score: {score(s.get('review'))}")
            lines.append("")

            lint = s.get("lint_issues") if isinstance(s.get("lint_issues"), list) else []
            if lint:
                lines.append("**Linter issues**")
                lines.append("")
                lines.extend([f"- {it}" for it in lint])
                lines.append("")

            issues = s.get("review", {}).get("issues") if isinstance(s.get("review"), dict) else []
            if isinstance(issues, list) and issues:
                lines.append("**LLM reported issues**")
                lines.append("")
                lines.extend([f"- {str(it)}" for it in issues])
                lines.append("")

            sugg = s.get("review", {}).get("suggestions") if isinstance(s.get("review"), dict) else []
            if isinstance(sugg, list) and sugg:
                lines.append("**Actionable suggestions (not abbreviated)**")
                lines.append("")
                lines.extend([f"- {str(it)}" for it in sugg])
                lines.append("")

    write_text_atomic(Path(run_dir) / "quality_report.md", "\n".join(lines) + "\n")


def capture(
    *,
    repo_root: str | Path,
    topic: str,
    domain: str | None,
    all_domains: bool,
    total: int | None,
    per_source: int | None,
    provider: str | None,
    offline: bool,
    publish: bool,
    publish_overwrite: bool,
    pretty: bool,
    tags: list[str] | None = None,
) -> Path:
    load_dotenv(repo_root)
    llm = create_llm_from_env(provider_override=provider)

    all_names = sorted(DOMAIN_CONFIG.keys())
    forced = str(domain or "").strip().lower() or None
    if forced and forced not in all_names:
        raise RuntimeError(f"Unknown domain: {forced} (expected one of: {', '.join(all_names)})")

    if all_domains:
        run_domains = all_names
    elif forced:
        run_domains = [forced]
    else:
        run_domains = [classify_domain_by_llm(topic=topic, domains=all_names, llm=llm)]

    per_domain_totals: dict[str, int] = {}
    if total is not None:
        t = max(1, min(150 * len(run_domains), int(total)))
        base = t // len(run_domains)
        rem = t % len(run_domains)
        for i, d in enumerate(run_domains):
            per_domain_totals[d] = base + (1 if i < rem else 0)

    counts_by_domain: dict[str, dict[str, int]] = {}
    target_total = 0
    for d in run_domains:
        cfg = DOMAIN_CONFIG[d]
        if d in per_domain_totals:
            counts = compute_method_counts(config=cfg, total=per_domain_totals[d], per_source=None)
        else:
            counts = compute_method_counts(config=cfg, total=None, per_source=per_source)
        counts_by_domain[d] = counts
        target_total += int(counts.get("web") or 0) + int(counts.get("github") or 0) + int(counts.get("forum") or 0) + int(counts.get("arxiv") or 0)

    run_dir = make_run_dir(repo_root, topic)
    ensure_dir(run_dir)

    # Write an initial manifest early for auditability. This ensures that even if the run
    # is interrupted mid-flight, there is a stable record under captures/<run-id>/.
    manifest_path = Path(run_dir) / "manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": Path(run_dir).name,
        "topic_input": topic,
        "generated_at": utc_now_iso_z(),
        "cli_options": {
            "all": bool(all_domains),
            "domain": forced,
            "provider": getattr(llm, "provider", ""),
            "model": getattr(llm, "model", ""),
            "publish": bool(publish),
            "publish_overwrite": bool(publish_overwrite),
            "offline": bool(offline),
            "total_input": int(total) if total is not None else None,
            "per_source_input": int(per_source) if per_source is not None else None,
            "per_domain_totals": per_domain_totals or None,
        },
        "domains": [],
        "domain_config": DOMAIN_CONFIG,
    }
    write_json_atomic(manifest_path, manifest)

    domain_results: list[dict[str, Any]] = []
    for d in run_domains:
        cfg = DOMAIN_CONFIG[d]
        try:
            r = generate_domain_batch(
                repo_root=repo_root,
                run_dir=run_dir,
                domain=d,
                config=cfg,
                topic=topic,
                llm=llm,
                counts=counts_by_domain[d],
                tags=tags,
                offline=offline,
                pretty=pretty,
            )
            domain_results.append(r)
        except Exception as e:
            domain_results.append(
                {
                    "domain": d,
                    "topic_input": topic,
                    "counts_requested": counts_by_domain[d],
                    "web": [],
                    "github": [],
                    "forum": [],
                    "web_errors": [str(e)],
                    "github_errors": [str(e)],
                    "forum_errors": [str(e)],
                }
            )

    manifest["domains"] = domain_results
    write_json_atomic(manifest_path, manifest)
    render_quality_report(run_dir=run_dir, run_manifest=manifest)

    return Path(run_dir)
