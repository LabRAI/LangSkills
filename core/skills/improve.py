from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url
from ..llm.types import ChatMessage, LlmClient
from ..sources.github import github_fetch_readme_excerpt_raw, parse_github_full_name_from_url
from ..sources.stackoverflow import (
    combine_question_answer_text,
    parse_stackoverflow_question_id,
    pick_answer_for_question,
    stack_fetch_answers_with_body,
    stack_fetch_questions_with_body,
)
from ..sources.webpage import fetch_webpage_text
from ..utils.fs import ensure_dir, read_json, read_text, resolve_run_dir, write_json_atomic, write_text_atomic
from ..utils.hashing import sha256_hex
from ..utils.md import lint_skill_markdown
from ..utils.time import utc_now_iso_z
from ..utils.text import html_to_text, truncate_text
from ..utils.yaml_simple import parse_metadata_yaml_text, write_metadata_yaml_text
from .coerce import coerce_markdown, coerce_string
from .markdown_ops import (
    ensure_at_least_one_code_block,
    ensure_evidence_section,
    ensure_verification_has_code_block,
    ensure_sources_contain_url,
    ensure_triad_sections,
    strip_raw_urls_outside_sources,
)
from .package_v2 import build_skill_package_v2_with_llm


def extract_suggestions(review: Any) -> list[str]:
    if not isinstance(review, dict):
        return []
    arr = review.get("suggestions")
    if not isinstance(arr, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for x in arr:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 20:
            break
    return out


def strip_urls_for_prompt(text: str) -> str:
    return re.sub(r"https?://\S+", "<URL>", str(text or ""))


def fetch_source_excerpt_for_improve(*, source_type: str, source_url: str) -> str:
    t = str(source_type or "").strip()
    url = str(source_url or "").strip()
    if not t or not url:
        return ""

    if t == "webpage":
        r = fetch_webpage_text(url, timeout_ms=25_000, retries=2)
        return truncate_text(strip_urls_for_prompt(r.extracted_text), 8000)

    if t == "github":
        full_name = parse_github_full_name_from_url(url)
        if not full_name:
            return ""
        readme = github_fetch_readme_excerpt_raw(full_name=full_name, default_branch="main")
        return truncate_text(strip_urls_for_prompt(readme), 8000)

    if t == "forum":
        qid = parse_stackoverflow_question_id(url)
        if not qid:
            return ""
        questions = stack_fetch_questions_with_body(question_ids=[qid])
        answers = stack_fetch_answers_with_body(question_ids=[qid])
        q0 = questions[0] if questions else None
        if not q0:
            return ""
        a0 = pick_answer_for_question(q0, answers)
        combined = combine_question_answer_text(q0, a0)
        return truncate_text(strip_urls_for_prompt(combined), 8000)

    return ""


def make_rewrite_skill_prompt(
    *,
    domain: str,
    skill_id: str,
    source_url: str,
    title: str,
    current_skill_md: str,
    required_suggestions: list[str],
    must_fix_suggestions: list[str],
    lint_issues: list[str],
    source_excerpt: str,
    skill_kind: str | None = None,
) -> list[ChatMessage]:
    kind = str(skill_kind or "").strip().lower()
    base_lines = [
        "You are a senior technical writer.",
        "You will REWRITE an existing skill markdown in English to address ALL required suggestions.",
        "Do not omit any suggestion: every item in required_suggestions must be addressed in the rewritten skill.",
        "",
        "Output ONLY a JSON object with keys:",
        "- skill_md: string (the full markdown)",
        "- evidence: array (length N) of objects {idx:number, quote:string}",
        "- review_after: object {overall_score:number(1-5), issues: string[]}",
        "- rewrite_summary: string",
        "",
        "Evidence rules:",
        "- Let N = len(required_suggestions). evidence MUST be an array of length N, and evidence[i-1].idx MUST equal i.",
        "- quote MUST be an exact substring copied from skill_md (<= 20 words) that proves the suggestion is addressed.",
        "- Never restate the suggestion as quote. The quote must come from the actual skill_md content (for links/resources, quote a URL line from Sources).",
        "- If you did NOT address a suggestion, set quote to an empty string.",
        "- Do NOT paste required_suggestions verbatim into skill_md; they are not part of the final skill.",
        "",
        "General rules:",
        "- Keep raw URLs in Sources; avoid raw URLs in prose. If a runnable snippet needs a URL, keep it inside fenced code blocks.",
        "- Sources must include the provided source_url and no more than 5 additional trustworthy URLs.",
        "- Also fix any items in lint_issues (treat them as mandatory).",
    ]

    if kind == "paper_writing":
        section_lines = [
            "Markdown section order:",
            "# <Title>",
            "## Audience",
            "## Key Contributions",
            "## Method Overview",
            "## Experiments",
            "## Limitations",
            "## Writing Outline",
            "## Steps",
            "## Verification",
            "## Safety",
            "## Evidence",
            "## Sources",
            "Rules:",
            "- Key Contributions: 3-6 bullet claims (concise, testable).",
            "- Writing Outline: include a fenced code block that writes article_outline.md (markdown skeleton).",
            "- Steps: 5-12 numbered steps using '1. ...'.",
            "- Verification: include a fenced bash block that writes/updates article_outline.md and echoes success.",
        ]
    elif kind == "paper_writeup":
        section_lines = [
            "Markdown section order:",
            "# <Title>",
            "## Audience",
            "## Topic",
            "## Introduction",
            "## Method Innovation Summary",
            "## Experiment Design and Analysis",
            "## Method Paragraph",
            "## Figure Caption",
            "## Steps",
            "## Verification",
            "## Safety",
            "## Evidence",
            "## Sources",
            "Rules:",
            "- Steps: 5-10 numbered steps using '1. ...'.",
            "- Verification: include a fenced bash block that writes paper_writeup.md and echoes success.",
        ]
    elif kind == "experiment_design":
        section_lines = [
            "Markdown section order:",
            "# <Title>",
            "## Audience",
            "## Claims and Metrics",
            "## Datasets and Baselines",
            "## Experiment Plan",
            "## Risks and Observability",
            "## Steps",
            "## Verification",
            "## Safety",
            "## Evidence",
            "## Sources",
            "Rules:",
            "- Claims and Metrics: include a markdown table (Claim | Metric | Dataset | Baseline).",
            "- Steps: 6-12 numbered steps using '1. ...'.",
            "- Verification: include a fenced bash block that creates experiment_plan.md and checklist.yaml skeletons.",
        ]
    else:
        section_lines = [
            "Markdown rules for skill_md:",
            "- Use this exact section structure (English headings):",
            "# <Title>",
            "## Background",
            "## Use Cases",
            "## Inputs",
            "## Outputs",
            "## Steps",
            "## Verification",
            "## Safety",
            "## Sources",
            "- In Steps, use numbered list '1. ...' and keep <= 12 steps.",
            "- Must include at least 1 fenced code block ```...``` (commands/snippets).",
        ]

    system = "\n".join(base_lines + [""] + section_lines)

    user = json.dumps(
        {
            "meta": {"domain": domain, "skill_id": skill_id, "title": title or "", "source_url": source_url},
            "current_skill_md": current_skill_md or "",
            "required_suggestions": required_suggestions or [],
            "must_fix_suggestions": must_fix_suggestions or [],
            "lint_issues": lint_issues or [],
            "source_excerpt": source_excerpt or "",
        },
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_evidence_only_prompt(
    *,
    domain: str,
    skill_id: str,
    source_url: str,
    required_suggestions: list[str],
    skill_md: str,
) -> list[ChatMessage]:
    system = "\n".join(
        [
            "You produce evidence quotes for an existing skill markdown.",
            "Output ONLY a JSON object with key: evidence.",
            "",
            "Let N = len(required_suggestions). evidence MUST be an array of length N, and evidence[i-1].idx MUST equal i.",
            "Each item: {idx:number, quote:string}.",
            "- quote MUST be an exact substring copied from skill_md (<= 20 words).",
            "- If the suggestion is not addressed, quote must be an empty string.",
            "- Never restate the suggestion as quote.",
        ]
    )
    user = json.dumps(
        {
            "meta": {"domain": domain, "skill_id": skill_id, "source_url": source_url},
            "required_suggestions": required_suggestions or [],
            "skill_md": skill_md or "",
        },
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def normalize_evidence(required_suggestions: list[str], evidence: Any) -> list[dict[str, Any]]:
    req = list(required_suggestions or [])
    ev = evidence if isinstance(evidence, list) else []
    normalized: list[dict[str, Any]] = []
    for i, suggestion in enumerate(req, start=1):
        row: Any = next((x for x in ev if isinstance(x, dict) and int(x.get("idx") or 0) == i), None)
        if row is None and i - 1 < len(ev):
            row = ev[i - 1]
        row = row if isinstance(row, dict) else {}
        normalized.append({"idx": i, "suggestion": str(suggestion or ""), "quote": coerce_string(row.get("quote")).strip()})
    return normalized


def missing_suggestions_from_evidence(evidence: list[dict[str, Any]], skill_md: str) -> list[str]:
    md = str(skill_md or "")
    missing: list[str] = []
    for it in evidence or []:
        quote = str(it.get("quote") or "").strip()
        suggestion = str(it.get("suggestion") or "")
        if not suggestion:
            continue
        if not quote or quote not in md:
            missing.append(suggestion)
    return missing


def build_evidence_quotes_with_llm(
    *,
    llm: LlmClient,
    domain: str,
    skill_id: str,
    source_url: str,
    required_suggestions: list[str],
    skill_md: str,
) -> list[dict[str, Any]]:
    messages = make_evidence_only_prompt(
        domain=domain,
        skill_id=skill_id,
        source_url=source_url,
        required_suggestions=required_suggestions,
        skill_md=skill_md,
    )
    out: dict | None = None
    last_err: Exception | None = None
    for attempt in range(0, 3):
        try:
            out = llm.chat_json(messages=messages, temperature=0.0, timeout_ms=60_000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if not isinstance(out, dict):
        raise RuntimeError("Evidence: unknown error") from last_err

    normalized = normalize_evidence(required_suggestions, out.get("evidence"))
    # Enforce substring rule deterministically.
    md = str(skill_md or "")
    return [{**it, "quote": (it["quote"] if it["quote"] and it["quote"] in md else "")} for it in normalized]


@dataclass
class ImproveResult:
    passes: int
    lint_before: list[str]
    lint_after: list[str]
    missing_suggestions: list[str]


def improve_one_skill_in_place(
    *,
    run_dir: str | Path,
    domain: str,
    method_key: str,
    skill_entry: dict[str, Any],
    llm: LlmClient,
    max_passes: int,
) -> ImproveResult:
    rel_dir = str(skill_entry.get("rel_dir") or "").strip()
    if not rel_dir:
        raise RuntimeError("Missing rel_dir")
    skill_dir = Path(run_dir) / rel_dir
    skill_path = skill_dir / "skill.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Missing skill.md: {rel_dir}")

    original_md = read_text(skill_path)
    backup_path = skill_dir / "skill.original.md"
    if not backup_path.exists():
        write_text_atomic(backup_path, original_md)

    meta_path = skill_dir / "metadata.yaml"
    meta = parse_metadata_yaml_text(read_text(meta_path)) if meta_path.exists() else {}
    skill_kind = str(skill_entry.get("skill_kind") or meta.get("skill_kind") or "").strip().lower()

    required_suggestions = extract_suggestions(skill_entry.get("review"))
    lint_before = lint_skill_markdown(original_md)

    source_excerpt = ""
    if str(os.environ.get("LANGSKILLS_IMPROVE_FETCH_SOURCE") or "").strip() == "1":
        source_excerpt = fetch_source_excerpt_for_improve(
            source_type=str(skill_entry.get("source_type") or skill_entry.get("method") or ""),
            source_url=str(skill_entry.get("source_url") or ""),
        )

    working_md = original_md
    best_md = original_md
    best_evidence = normalize_evidence(required_suggestions, [])
    best_lint = lint_before[:]
    best_missing = required_suggestions[:]
    best_review_after = {"overall_score": 0, "issues": []}
    best_summary = ""

    pass_count = 0
    must_fix_suggestions = best_missing[:]
    lint_issues = best_lint[:]

    def score(lint_count: int, missing_count: int) -> int:
        return lint_count * 100 + missing_count

    while pass_count < max(1, int(max_passes or 1)):
        pass_count += 1

        messages = make_rewrite_skill_prompt(
            domain=domain,
            skill_id=str(skill_entry.get("id") or ""),
            source_url=str(skill_entry.get("source_url") or ""),
            title=str(skill_entry.get("title") or ""),
            current_skill_md=working_md,
            required_suggestions=required_suggestions,
            must_fix_suggestions=must_fix_suggestions,
            lint_issues=lint_issues,
            source_excerpt=source_excerpt,
            skill_kind=skill_kind,
        )

        out: dict | None = None
        last_err: Exception | None = None
        for attempt in range(0, 2):
            try:
                out = llm.chat_json(messages=messages, temperature=0.2 if attempt == 0 else 0.0, timeout_ms=120_000)
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(0.6 * (attempt + 1))
        if not isinstance(out, dict):
            raise RuntimeError("Rewrite failed") from last_err

        candidate_md = coerce_markdown(out.get("skill_md"))
        if not candidate_md.strip() or not re.match(r"^#\s+", candidate_md.strip()):
            candidate_md = working_md

        # Enforce invariants.
        source_url = str(skill_entry.get("source_url") or "").strip()
        candidate_md = ensure_sources_contain_url(candidate_md, source_url)
        run_id = Path(run_dir).name
        evidence_lines = [f"- run_id: {run_id}"]
        artifact_id = str(skill_entry.get("source_artifact_id") or meta.get("source_artifact_id") or "").strip()
        if artifact_id:
            evidence_lines.append(f"- source_artifact: captures/{run_id}/sources/{artifact_id}.json")
        candidate_md = ensure_evidence_section(candidate_md, evidence_lines)
        candidate_md = strip_raw_urls_outside_sources(candidate_md)
        candidate_md = ensure_at_least_one_code_block(candidate_md)
        candidate_md = ensure_verification_has_code_block(candidate_md)
        if skill_kind not in {"paper_writing", "paper_writeup", "experiment_design"}:
            candidate_md = ensure_triad_sections(candidate_md)

        lint_after = lint_skill_markdown(candidate_md)

        evidence = normalize_evidence(required_suggestions, out.get("evidence"))
        if required_suggestions and (not isinstance(out.get("evidence"), list) or len(out.get("evidence")) != len(required_suggestions)):
            evidence = build_evidence_quotes_with_llm(
                llm=llm,
                domain=domain,
                skill_id=str(skill_entry.get("id") or ""),
                source_url=source_url,
                required_suggestions=required_suggestions,
                skill_md=candidate_md,
            )
        else:
            md0 = str(candidate_md or "")
            evidence = [{**it, "quote": (it["quote"] if it["quote"] and it["quote"] in md0 else "")} for it in evidence]

        missing = missing_suggestions_from_evidence(evidence, candidate_md)

        review_after = out.get("review_after") if isinstance(out.get("review_after"), dict) else {}
        candidate_review_after = {
            "overall_score": float(review_after.get("overall_score") or 0),
            "issues": [str(x) for x in (review_after.get("issues") if isinstance(review_after.get("issues"), list) else [])],
        }
        candidate_summary = coerce_string(out.get("rewrite_summary")).strip()

        cand_score = score(len(lint_after), len(missing))
        best_score = score(len(best_lint), len(best_missing))
        if cand_score < best_score:
            best_md = candidate_md
            best_evidence = evidence
            best_lint = lint_after
            best_missing = missing
            best_review_after = candidate_review_after
            best_summary = candidate_summary

        working_md = best_md
        must_fix_suggestions = best_missing[:]
        lint_issues = best_lint[:]

        if not best_missing and not best_lint:
            break

    write_text_atomic(skill_path, best_md)
    write_json_atomic(
        skill_dir / "improvement.json",
        {
            "improved_at": utc_now_iso_z(),
            "id": str(skill_entry.get("id") or ""),
            "title": str(skill_entry.get("title") or ""),
            "domain": domain,
            "method": method_key,
            "source_url": str(skill_entry.get("source_url") or ""),
            "passes": pass_count,
            "lint_before": lint_before,
            "lint_after": best_lint,
            "suggestions": required_suggestions,
            "evidence": best_evidence,
            "missing_suggestions": best_missing,
            "review_after": best_review_after,
            "rewrite_summary": best_summary,
        },
    )

    # Regenerate package files based on improved skill.md.
    source_url = str(meta.get("source_url") or skill_entry.get("source_url") or "").strip()
    canon_url = canonicalize_source_url(source_url) or source_url
    artifact_id = str(meta.get("source_artifact_id") or skill_entry.get("source_artifact_id") or "").strip()
    if not artifact_id and canon_url:
        artifact_id = sha256_hex(canon_url)
    if artifact_id:
        src_path = Path(run_dir) / "sources" / f"{artifact_id}.json"
        src_obj = read_json(src_path, default=None)
        fetched_at = str(src_obj.get("fetched_at") or "").strip() if isinstance(src_obj, dict) else ""
        if fetched_at:
            meta["source_fetched_at"] = fetched_at
    now_iso = utc_now_iso_z()
    pkg = build_skill_package_v2_with_llm(
        llm=llm,
        domain=str(meta.get("domain") or domain),
        method=str(meta.get("source_type") or method_key),
        skill_id=str(meta.get("id") or skill_entry.get("id") or ""),
        title=str(meta.get("title") or skill_entry.get("title") or ""),
        source_url=canon_url or source_url,
        source_fetched_at=str(meta.get("source_fetched_at") or ""),
        package_generated_at=now_iso,
        license_spdx=str(meta.get("license_spdx") or ""),
        license_risk=str(meta.get("license_risk") or ""),
        skill_md=best_md,
        source_excerpt=source_excerpt,
    )

    write_text_atomic(skill_dir / "library.md", pkg.library_md)
    ref_dir = skill_dir / "reference"
    ensure_dir(ref_dir)
    write_text_atomic(ref_dir / "sources.md", pkg.reference["sources_md"])
    write_text_atomic(ref_dir / "troubleshooting.md", pkg.reference["troubleshooting_md"])
    write_text_atomic(ref_dir / "edge-cases.md", pkg.reference["edge_cases_md"])
    write_text_atomic(ref_dir / "examples.md", pkg.reference["examples_md"])
    write_text_atomic(ref_dir / "changelog.md", pkg.reference["changelog_md"])

    meta_out = dict(meta)
    meta_out["package_schema_version"] = 2
    meta_out["package_generated_at"] = now_iso
    meta_out["package_llm_provider"] = getattr(llm, "provider", "")
    meta_out["package_llm_model"] = getattr(llm, "model", "")
    if canon_url:
        meta_out["source_url"] = canon_url
    if artifact_id:
        meta_out["source_artifact_id"] = artifact_id
    if meta_path.exists():
        write_text_atomic(meta_path, write_metadata_yaml_text(meta_out))

    return ImproveResult(passes=pass_count, lint_before=lint_before, lint_after=best_lint, missing_suggestions=best_missing)


def improve_run_in_place(*, repo_root: str | Path, run_target: str, llm: LlmClient, max_passes: int) -> dict[str, Any]:
    run_dir = resolve_run_dir(repo_root, run_target)
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in: {run_dir}")
    before_manifest_path = Path(run_dir) / "manifest.before.json"
    if not before_manifest_path.exists():
        write_text_atomic(before_manifest_path, manifest_path.read_text(encoding="utf-8"))

    quality_path = Path(run_dir) / "quality_report.md"
    quality_before_path = Path(run_dir) / "quality_report.before.md"
    if quality_path.exists() and not quality_before_path.exists():
        write_text_atomic(quality_before_path, read_text(quality_path))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    only = str(os.environ.get("LANGSKILLS_IMPROVE_ONLY") or "").strip()

    def _load_arxiv_entries() -> list[dict[str, Any]]:
        path = Path(run_dir) / "arxiv_results.json"
        data = read_json(path, default=None)
        if not isinstance(data, dict):
            return []
        out: list[dict[str, Any]] = []
        for row in data.get("results") if isinstance(data.get("results"), list) else []:
            if not isinstance(row, dict):
                continue
            skill = row.get("skill") if isinstance(row.get("skill"), dict) else None
            if not skill:
                continue
            rel_dir = str(skill.get("rel_dir") or "").strip()
            if not rel_dir:
                continue
            entry = dict(skill)
            entry["rel_dir"] = rel_dir
            entry["source_url"] = str(skill.get("source_url") or row.get("source_url") or "").strip()
            entry["source_type"] = str(skill.get("source_type") or "arxiv").strip()
            entry["review"] = skill.get("review") if isinstance(skill.get("review"), dict) else {}
            meta_path = Path(run_dir) / rel_dir / "metadata.yaml"
            if meta_path.exists():
                meta = parse_metadata_yaml_text(read_text(meta_path))
                entry["source_artifact_id"] = str(meta.get("source_artifact_id") or entry.get("source_artifact_id") or "").strip()
                entry["skill_kind"] = str(meta.get("skill_kind") or entry.get("skill_kind") or "").strip()
                entry["domain"] = str(meta.get("domain") or entry.get("domain") or "").strip() or "research"
                entry["title"] = str(meta.get("title") or entry.get("title") or "").strip()
                entry["source_url"] = str(meta.get("source_url") or entry.get("source_url") or "").strip()
            if only and str(entry.get("id") or "").strip() != only:
                continue
            out.append(entry)
        return out

    domains = manifest.get("domains") if isinstance(manifest.get("domains"), list) else []
    arxiv_entries = _load_arxiv_entries() if not domains else []
    if arxiv_entries:
        by_domain: dict[str, list[dict[str, Any]]] = {}
        for entry in arxiv_entries:
            d = str(entry.get("domain") or "research").strip() or "research"
            by_domain.setdefault(d, []).append(entry)
        manifest["domains"] = [{"domain": d, "arxiv": entries} for d, entries in by_domain.items()]
        domains = manifest.get("domains") if isinstance(manifest.get("domains"), list) else []

    method_keys: list[str] = ["web", "github", "forum"]
    if any(isinstance(d, dict) and isinstance(d.get("arxiv"), list) and d.get("arxiv") for d in domains):
        method_keys.append("arxiv")

    results: list[dict[str, Any]] = []

    for d in domains:
        if not isinstance(d, dict):
            continue
        domain = str(d.get("domain") or "").strip()
        for method_key in method_keys:
            arr = d.get(method_key) if isinstance(d.get(method_key), list) else []
            for s in arr:
                if not isinstance(s, dict):
                    continue
                if only and str(s.get("id") or "").strip() != only:
                    continue
                try:
                    r = improve_one_skill_in_place(
                        run_dir=run_dir,
                        domain=domain,
                        method_key=method_key,
                        skill_entry=s,
                        llm=llm,
                        max_passes=max_passes,
                    )
                    ok = (not r.lint_after) and (not r.missing_suggestions)
                    results.append({"id": str(s.get("id") or ""), "ok": bool(ok), "missing": r.missing_suggestions, "lint": r.lint_after})
                except Exception as e:
                    results.append({"id": str(s.get("id") or ""), "ok": False, "error": str(e)})

    manifest["improved_at"] = utc_now_iso_z()
    manifest["improvement_summary"] = {
        "total": len(results),
        "ok": sum(1 for x in results if x.get("ok") is True),
        "failed": sum(1 for x in results if x.get("ok") is not True),
    }

    write_json_atomic(Path(run_dir) / "manifest.json", manifest)
    from .generate import render_quality_report

    render_quality_report(run_dir=run_dir, run_manifest=manifest)

    # Post-check (recompute from files, like legacy).
    post: list[dict[str, Any]] = []
    lint_count = 0
    missing_count = 0
    for d in domains:
        if not isinstance(d, dict):
            continue
        for method_key in method_keys:
            arr = d.get(method_key) if isinstance(d.get(method_key), list) else []
            for s in arr:
                if not isinstance(s, dict):
                    continue
                rel_dir = str(s.get("rel_dir") or "").strip()
                if not rel_dir:
                    continue
                skill_dir = Path(run_dir) / rel_dir
                skill_path = skill_dir / "skill.md"
                if not skill_path.exists():
                    continue
                md = read_text(skill_path)
                lint = lint_skill_markdown(md)
                improvement_path = skill_dir / "improvement.json"
                imp = {}
                if improvement_path.exists():
                    try:
                        imp = json.loads(improvement_path.read_text(encoding="utf-8"))
                    except Exception:
                        imp = {}
                missing = [str(x) for x in (imp.get("missing_suggestions") if isinstance(imp.get("missing_suggestions"), list) else [])]
                if lint:
                    lint_count += len(lint)
                if missing:
                    missing_count += len(missing)
                post.append({"id": str(s.get("id") or ""), "rel_dir": rel_dir, "lint_issues": lint, "missing_suggestions": missing})

    write_text_atomic(
        Path(run_dir) / "post_check.md",
        "\n".join(
            [
                "# Post Check",
                "",
                f"- Checked at: {utc_now_iso_z()}",
                f"- Lint issues total: {lint_count}",
                f"- Missing suggestions total: {missing_count}",
                "",
                "If lint issues or missing suggestions > 0, re-run:",
                "",
                "```bash",
                f"py langskills_cli.py improve {Path(run_dir).name}",
                "```",
                "",
            ]
        )
        + "\n",
    )

    write_json_atomic(
        Path(run_dir) / "post_check.json",
        {
            "checked_at": utc_now_iso_z(),
            "lint_issues_total": lint_count,
            "missing_suggestions_total": missing_count,
            "skills": post,
        },
    )

    return {"run_dir": str(run_dir), "results": results, "lintCount": lint_count, "missingCount": missing_count}
