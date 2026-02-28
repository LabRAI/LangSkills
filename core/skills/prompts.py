from __future__ import annotations

import json
from typing import Any

from ..llm.types import ChatMessage
from ..utils.text import truncate_text


def make_skill_prompt(
    *,
    domain: str,
    method: str,
    skill_id: str,
    source_url: str,
    source_title: str,
    extracted_text: str,
    extra_context: dict[str, Any] | None,
    skill_kind: str | None = None,
) -> list[ChatMessage]:
    meta = {
        "domain": domain,
        "method": method,
        "skill_id": skill_id,
        "source_url": source_url,
        "source_title": source_title or "",
    }

    kind = (skill_kind or extra_context.get("skill_kind") if isinstance(extra_context, dict) else None) or ""
    kind = str(kind).strip().lower()
    language = str(extra_context.get("language") if isinstance(extra_context, dict) else "" or "en").strip()

    if kind == "paper_writing":
        system_lines = [
            "You are a senior research communicator who turns an arXiv paper into an actionable writing plan.",
            f"Write in {language or 'English'} with concise, original wording (no large quotes).",
            "Output ONLY a JSON object with keys: title, skill_md, review.",
            "skill_md MUST be a single markdown string.",
            "review must include: overall_score (1-5), issues (array), suggestions (array of 10-15 actionable edits).",
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
            "- Key Contributions: 3-6 bullet claims (no quotes); keep each concise and testable.",
            "- Writing Outline: provide a fenced code block that writes article_outline.md (markdown skeleton with headings + bullet prompts).",
            "- Steps: 5-12 numbered steps that end with a usable draft outline; avoid vague verbs.",
            "- Verification: must include a fenced bash block that writes/updates article_outline.md and echoes a success message.",
            "- Safety: include any ethical or attribution cautions relevant to summarizing research.",
            "- Sources: list ONLY the provided source URL(s).",
            "- Evidence: include audit pointers like run_id / captures path; no raw URLs.",
        ]
    elif kind == "experiment_design":
        system_lines = [
            "You are an experiment design lead turning a paper (and optional repo context) into a reproducible plan.",
            f"Write in {language or 'English'} with precise, original instructions.",
            "Output ONLY a JSON object with keys: title, skill_md, review.",
            "skill_md MUST be a single markdown string.",
            "review must include: overall_score (1-5), issues (array), suggestions (array of 10-15 precise edits).",
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
            "- Claims and Metrics: add a markdown table (Claim | Metric | Dataset | Baseline).",
            "- Experiment Plan: phased outline (minimal reproduction -> full -> ablations); include resources (GPU/CPU/time).",
            "- Steps: 6-12 numbered, concrete actions referencing configs/scripts if available; avoid speculation.",
            "- Verification: include a fenced bash block that creates experiment_plan.md and checklist.yaml skeletons (cat <<'EOF' > file ...).",
            "- Safety: include compute cost or data privacy cautions when relevant.",
            "- No raw URLs outside Sources; keep URLs inside Sources only.",
            "- Evidence: include audit pointers like run_id / captures path; no raw URLs.",
        ]
    elif kind == "paper_writeup":
        system_lines = [
            "You are a senior research communicator who produces a concise write-up from an arXiv paper.",
            f"Write in {language or 'English'} with precise, original wording (no large quotes).",
            "Output ONLY a JSON object with keys: title, skill_md, review.",
            "skill_md MUST be a single markdown string.",
            "review must include: overall_score (1-5), issues (array), suggestions (array of 10-15 actionable edits).",
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
            "- Topic: 1 concise sentence or noun phrase that captures the research focus.",
            "- Introduction: write 1 short paragraph plus 3-5 bullet points on how to write/shape the introduction.",
            "- Method Innovation Summary: one paragraph highlighting novelty and differentiators.",
            "- Experiment Design and Analysis: one paragraph describing datasets, baselines, metrics, and analysis flow.",
            "- Method Paragraph: one paragraph describing the method in paper-ready prose.",
            "- Figure Caption: provide 1-3 caption options (1-2 sentences each) for a key method or experiment figure.",
            "- Steps: 5-10 numbered steps that produce the write-up; avoid vague verbs.",
            "- Verification: include a fenced bash block that writes paper_writeup.md with the above sections and echoes success.",
            "- Safety: include attribution and hallucination cautions relevant to summarizing research.",
            "- Sources: list ONLY the provided source URL(s).",
            "- Evidence: include audit pointers like run_id / captures path; no raw URLs.",
        ]
    else:
        system_lines = [
            "You are a senior technical writer.",
            "Generate a high-quality, practical skill in English.",
            "Output ONLY a JSON object with keys: title, skill_md, review.",
            "skill_md MUST be a single markdown string (not an object, not an array).",
            "review must include: overall_score (1-5), issues (array), suggestions (array).",
            "In review.suggestions, output 10-15 specific and editable improvement suggestions (do not be generic, do not abbreviate).",
            "Do NOT quote large chunks from the source; write original instructions.",
            "Use ONLY the provided extracted_text. If required information is missing, write 'not provided' and do not infer.",
            "Use this exact markdown section structure in skill_md:",
            "# <Title>",
            "## Background",
            "## Use Cases",
            "## Inputs",
            "## Outputs",
            "## Steps",
            "## Verification",
            "## Safety",
            "## Evidence",
            "## Sources",
            "",
            "In Steps, use numbered list '1. ...' and keep <= 12 steps.",
            "Every step must map to a concrete point from extracted_text; if a step cannot be supported, write 'not provided' for that step.",
            "Must include at least 1 fenced code block ```...``` (commands/snippets).",
            "Verification must be executable and based only on extracted_text; do not invent commands, files, parameters, or outputs.",
            "In Sources, list ONLY the provided source URL(s). Avoid raw URLs in prose; if a runnable snippet needs a URL, keep it inside fenced code blocks.",
            "In Evidence, include at least one audit pointer such as:",
            "- a run id like `run-YYYY-MM-DD-...` (or `captures/run-*/...` paths)",
            "- a source artifact pointer like `captures/run-*/sources/<artifact>.json`",
            "Do NOT include raw URLs in Evidence.",
        ]

    system = "\n".join(system_lines)

    user = json.dumps(
        {"meta": meta, "extra_context": extra_context or {}, "extracted_text": extracted_text or ""},
        ensure_ascii=False,
        indent=2,
    )

    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_domain_router_prompt(*, topic: str, allowed_domains: list[str]) -> list[ChatMessage]:
    user = json.dumps(
        {
            "topic": topic,
            "allowed_domains": allowed_domains,
            "domain_descriptions": {
                "linux": "Linux/Unix shell, filesystem, processes, systemd, networking tools",
                "devtools": "Developer tooling: git, docker, CI, build/test tooling, packaging",
                "cloud": "Cloud & Kubernetes: k8s, containers in cluster, cloud services, infra ops",
                "data": "Data/SQL/analytics: DuckDB, PostgreSQL, pandas, data formats, query performance",
                "security": "Security: OWASP, authn/authz, JWT/OAuth, TLS/HTTPS, SSH hardening, common web vulns",
                "observability": "Observability: metrics/logs/traces, Prometheus, Grafana, OpenTelemetry, alerting",
                "web": "Web frontend: HTML/CSS/JS, React, Next.js, HTTP/Web APIs, TypeScript",
                "ml": "Machine learning: PyTorch, Transformers, fine-tuning/LoRA, evaluation, MLflow, vector search/RAG",
            },
        },
        ensure_ascii=False,
        indent=2,
    )

    return [
        ChatMessage(
            role="system",
            content="You are a router that classifies a user topic into a single domain. Output ONLY a JSON object with key 'domain'.",
        ),
        ChatMessage(role="user", content=user),
    ]


def make_skill_package_v2_prompt(
    *,
    domain: str,
    method: str,
    skill_id: str,
    title: str,
    source_url: str,
    source_fetched_at: str,
    package_generated_at: str,
    license_spdx: str,
    license_risk: str,
    skill_md: str,
    source_excerpt: str,
) -> list[ChatMessage]:
    meta = {
        "task": "package_v2",
        "domain": domain,
        "method": method,
        "skill_id": skill_id,
        "title": title or "",
        "source_url": source_url,
        "source_fetched_at": str(source_fetched_at or "").strip(),
        "package_generated_at": str(package_generated_at or "").strip(),
        "license_spdx": str(license_spdx or "").strip(),
        "license_risk": str(license_risk or "").strip(),
    }

    system = "\n".join(
        [
            "You are a senior technical writer.",
            "Generate a skill package (v2) in English for automation and distribution.",
            "",
            "Output ONLY a JSON object with keys:",
            "- library_md: string (markdown)",
            "- reference: object with keys sources_md, troubleshooting_md, edge_cases_md, examples_md, changelog_md (all markdown strings)",
            "",
            "Hard rules:",
            "- Do NOT quote large chunks from the source. Write original text.",
            "- Do NOT include any raw URLs in library_md or in reference.* except reference.sources_md.",
            "- In reference.sources_md, include ONLY the provided source_url as a raw URL (no other URLs).",
            "- library_md MUST include at least 1 fenced code block ```...``` with runnable commands/snippets.",
            "- Use meta.source_fetched_at as the access timestamp in sources_md if present (do NOT guess dates).",
            "- In changelog_md, the initial entry date MUST use meta.package_generated_at (date part, YYYY-MM-DD).",
            "- Avoid hard-coded calendar dates in examples/troubleshooting; prefer placeholders like YYYY-MM-DD unless derived from meta.",
            "",
            "library.md intent:",
            "- A copy-paste friendly minimal recipe. Keep it concise.",
            "",
            "reference/ intent (progressive disclosure):",
            "- sources_md: attribution + license notes + access timestamp (if available in meta).",
            "- troubleshooting_md: common failures + fixes.",
            "- edge_cases_md: non-obvious pitfalls + safe handling.",
            "- examples_md: 2-4 concrete examples, each with code blocks.",
            "- changelog_md: add an entry for today describing initial package generation.",
        ]
    )

    user = json.dumps(
        {
            "meta": meta,
            "skill_md": truncate_text(str(skill_md or ""), 8000),
            "source_excerpt": truncate_text(str(source_excerpt or ""), 4000),
        },
        ensure_ascii=False,
        indent=2,
    )

    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_skill_gate_prompt(
    *,
    domain: str,
    method: str,
    source_url: str,
    source_title: str,
    excerpt_text: str,
) -> list[ChatMessage]:
    meta = {
        "task": "skill_gate",
        "domain": str(domain or "").strip(),
        "method": str(method or "").strip(),
        "source_url": str(source_url or "").strip(),
        "source_title": str(source_title or "").strip(),
    }

    system = "\n".join(
        [
            "You are a strict reviewer deciding whether a source content is suitable to be converted into a practical technical skill.",
            "Output ONLY a JSON object with keys:",
            "- verdict: one of pass|maybe|fail",
            "- score: integer 0-10",
            "- reasons: array of <= 5 short strings (most important first)",
            "- good_signals: array of short strings (optional)",
            "- bad_signals: array of short strings (optional)",
            "",
            "Guidance:",
            "- pass: actionable and reusable; can be written as steps with verification.",
            "- maybe: has value but missing clarity/steps/verification; still potentially usable.",
            "- fail: too short, spam/marketing, pure opinion/news, or not actionable/reproducible.",
            "- Prefer fail if there is not enough concrete information to create a safe, verifiable skill.",
            "- Do NOT include any extra keys. Do NOT output markdown.",
        ]
    )

    user = json.dumps(
        {"meta": meta, "excerpt_text": str(excerpt_text or "")},
        ensure_ascii=False,
        indent=2,
    )

    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_repo_candidate_selector_prompt(
    *,
    target: str,
    language: str,
    top_n: int,
    symbol_pool: list[dict[str, Any]],
    docs_summary: str,
) -> list[ChatMessage]:
    """
    Ask the LLM to pick the best repo-based skill candidates from a symbol pool.
    The model must only use provided symbols (no hallucinated paths) and return JSON.
    """
    system = "\n".join(
        [
            "You are a senior software architect and technical writer selecting the most valuable skill candidates from a code symbol index.",
            "Use ONLY the provided symbols/paths/lines; do not invent anything.",
            "Output a strict JSON object (must not be empty) with structure:",
            "{\"candidates\": [ ... ]}",
            "candidates is an array; each element includes:",
            "{id,name,goal,target,entrypoints:[...],steps:[...],evidence:[{path,line,qualified_name?}],priority_score,reason}",
            "Rules:",
            "- evidence.path must come from the provided symbol list; line should be the symbol start_line or nearby; do not add unknown files.",
            "- priority_score 1-100; higher is more important; include a brief reason.",
            "- target must match the input target (cli/workflow/module/troubleshooting).",
            "- entrypoints must include at least 1 executable command; prefer `./.venv/bin/python langskills_cli.py ...`.",
            "- Do not include any URLs in entrypoints or steps (http:// https:// file://) or placeholders like <URL>; if needed, use plain text `URL`.",
            "- steps must be at least 3 actionable steps; do not add URLs.",
            "- Return at least 1 candidate, ideally top_n; never return an empty array.",
            "- Respond in the requested language.",
            "Example (illustrative only): {\"candidates\":[{\"id\":\"repo/workflow/foo\",\"name\":\"Workflow: foo\",\"goal\":\"...\",\"target\":\"workflow\",\"evidence\":[{\"path\":\"a/b.py\",\"line\":10}],\"priority_score\":90,\"reason\":\"entrypoint + writes files\"}]}",
        ]
    )

    user = json.dumps(
        {
            "target": target,
            "language": language,
            "top_n": int(top_n),
            "docs_summary": truncate_text(docs_summary, 4000),
            "symbol_pool": symbol_pool,
        },
        ensure_ascii=False,
        indent=2,
    )

    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_repo_tutorial_prompt(
    *,
    language: str,
    spec: dict[str, Any],
    code_snippets: list[dict[str, Any]],
    docs_summary: str,
    run_logs: str = "",
) -> list[ChatMessage]:
    """
    Ask the LLM to rewrite a SkillSpec into a human-friendly tutorial skill.
    Output JSON with skill_md/library_md/reference.*
    """
    system = "\n".join(
        [
            "You are a senior technical writer. Rewrite the SkillSpec into a runnable tutorial skill.",
            "Use only the provided context; do not invent paths/parameters/URLs. If information is missing, say \"not provided\".",
            f"Write in {language or 'English'} (except inside code blocks/identifiers).",
            "All commands must use `./.venv/bin/python langskills_cli.py ...` (do not use `py ...`).",
            "Output a strict JSON object:",
            "{skill_md, library_md, reference:{sources_md,troubleshooting_md,edge_cases_md,examples_md,changelog_md}}",
            "Hard requirements:",
            "- skill_md section order: # Title, ## Goal, ## Prerequisites, ## Steps, ## Verification, ## Outputs, ## Safety, ## Troubleshooting, ## Common Pitfalls, ## Sources, ## Evidence, ## Changelog",
            "- skill_md ## Verification must include a fenced code block (```bash ... ```), with at least 1 runnable command (prefer constraints.repo_query_entrypoint_template; QUERY must come from spec/evidence).",
            "- library_md must include at least 1 fenced code block and must not contain any URLs (http:// https:// file://).",
            "- reference.examples_md must include at least 1 fenced code block and must not contain any URLs anywhere (including code blocks); if a placeholder is needed, use plain `URL` without a scheme.",
            "- reference.sources_md must contain only constraints.source_url as a raw URL (no extra characters) and include `Accessed at: <constraints.source_fetched_at>`; do not include a second URL.",
            "- reference.changelog_md must include constraints.package_date (YYYY-MM-DD).",
            "- Outside reference.sources_md, do not include raw URLs. Evidence must include only given path:line or run_id; do not add URLs.",
            "- Do not leave <URL>/TODO; do not add extra links; keep the requested language.",
        ]
    )

    source_url = str(spec.get("source_url") or "").strip()
    source_fetched_at = str(spec.get("source_fetched_at") or spec.get("generated_at") or "").strip()
    package_date = (str(spec.get("generated_at") or "").strip() or "")[:10]

    index_path = str(spec.get("index_path") or "captures/symbol_index.jsonl").strip() or "captures/symbol_index.jsonl"
    user = json.dumps(
        {
            "language": language,
            "spec": spec,
            "constraints": {
                "source_url": source_url,
                "source_fetched_at": source_fetched_at,
                "package_date": package_date,
                "repo_query_entrypoint_template": f"./.venv/bin/python langskills_cli.py repo-query \"<query>\" --json --index {index_path}",
            },
            "code_snippets": code_snippets,
            "docs_summary": truncate_text(docs_summary, 4000),
            "run_logs": truncate_text(run_logs, 1200),
        },
        ensure_ascii=False,
        indent=2,
    )

    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_repo_symbol_summary_prompt(*, language: str, path: str, qualified_name: str, snippet: str) -> list[ChatMessage]:
    """
    Prompt to summarize a single symbol's code snippet into 1-2 sentences.
    """
    system = "\n".join(
        [
            "You are a senior software engineer. Read the code snippet and output a concise purpose summary.",
            "Use only the provided code; do not speculate about unseen behavior.",
            "Output strict JSON: {\"summary\": \"...\"} with no other fields.",
            "Write the summary in the requested language.",
        ]
    )
    user = json.dumps(
        {
            "language": language,
            "path": path,
            "qualified_name": qualified_name,
            "code_snippet": truncate_text(snippet, 4000),
        },
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_repo_file_selector_prompt(*, language: str, top_n: int, files: list[dict[str, Any]], docs_summary: str) -> list[ChatMessage]:
    system = "\n".join(
        [
            "You are a senior software engineer. From the file list, pick the most valuable files for skill generation.",
            "Use only the provided file list; do not invent paths.",
            "Output a strict JSON object (must not be empty): {\"files\":[...]}",
            "files is an array; each element includes {path, reason, priority_score} with priority_score 1-100.",
            f"Return at least 1 item, ideally top_n={top_n}.",
            "Write reasons in the requested language.",
        ]
    )
    user = json.dumps(
        {"language": language, "top_n": top_n, "docs_summary": truncate_text(docs_summary, 2000), "files": files},
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def make_repo_file_skill_prompt(
    *, language: str, path: str, content: str, target: str, top_n: int, index_path: str = "captures/symbol_index.jsonl"
) -> list[ChatMessage]:
    system = "\n".join(
        [
            "You are a senior software engineer. Based on a single file's content, propose skill candidates.",
            "Use only the file content; do not reference external information.",
            "Output a strict JSON object (must not be empty): {\"candidates\":[...]}",
            "Each candidate: {id,name,goal,target,entrypoints:[...],steps:[...],evidence:[{path,line}],priority_score,reason}",
            "entrypoints: array, at least 1 item; must be executable commands.",
            "For reproducibility, prefer repo-query (do not invent subcommands) using this template:",
            f"- `./.venv/bin/python langskills_cli.py repo-query \"<query>\" --json --index {str(index_path or 'captures/symbol_index.jsonl')}`",
            "<query> may use file paths/module names/function names (must come from this file).",
            "steps: array of 3-8 actionable steps (avoid vague explanations).",
            "Do NOT include `http://` / `https://` / `file://` anywhere in entrypoints or steps (including code blocks, backticks, or example commands), and do not use <URL> placeholders.",
            "If you must refer to an endpoint, use schemeless forms like `HOST:PORT/path` or `localhost:PORT/path`, or plain text `URL`.",
            "Bad example (forbidden): `curl http://localhost:8080/query`; good examples: `curl localhost:8080/query` or `curl URL`.",
            "evidence.line should be a line number in this file (approximate is OK). priority_score 1-100.",
            f"target is fixed to {target}.",
            f"At most {top_n} items, at least 1.",
            "Write names/goals/reasons in the requested language.",
        ]
    )
    user = json.dumps(
        {"language": language, "path": path, "target": target, "content": truncate_text(content, 6000), "top_n": top_n},
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
