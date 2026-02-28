from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..llm.factory import create_llm_from_env
from ..llm.types import ChatMessage
from ..skills.prompts import make_repo_tutorial_prompt
from ..utils.fs import list_skill_dirs, write_json_atomic, write_text_atomic
from ..utils.lang import resolve_output_language
from ..utils.md import count_fenced_code_blocks, find_raw_urls, lint_skill_markdown
from ..utils.redact import redact_obj, redact_text
from ..utils.text import truncate_text
from .llm_trace import write_llm_trace
from .symbol_index import load_symbol_index_jsonl


def _read_repo_docs_summary(repo_root: Path) -> str:
    parts: list[str] = []
    for p in [
        repo_root / "README.md",
        repo_root / "plan_githubagent.md",
        repo_root / "docs" / "repo_inventory.md",
        repo_root / "docs" / "verify_log.md",
        repo_root / "docs" / "mohu.md",
    ]:
        if p.exists():
            try:
                parts.append(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return "\n\n".join(parts)


def _code_snippets_from_evidence(repo_root: Path, spec: dict[str, Any], window: int = 40, max_snippets: int = 3) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    ev = spec.get("evidence") if isinstance(spec.get("evidence"), list) else []
    for e in ev[:max_snippets]:
        if not isinstance(e, dict):
            continue
        path = Path(repo_root / str(e.get("path") or ""))
        if not path.exists():
            continue
        try:
            line = int(e.get("line") or 1)
        except Exception:
            line = 1
        try:
            lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
        except Exception:
            continue
        start = max(0, line - window)
        end = min(len(lines), line + window)
        chunk = "\n".join(f"{i+1:>4}: {lines[i]}" for i in range(start, end))
        snippets.append({"path": str(path.relative_to(repo_root).as_posix()), "line": line, "code": chunk})
    return snippets


def rewrite_repo_skills_with_llm(
    *,
    repo_root: str | Path,
    pkg_dir: str | Path,
    language: str = "en",
    llm_model: str | None = None,
    timeout_ms: int = 300_000,
    symbols: list[dict[str, Any]] | None = None,
) -> None:
    repo_root = Path(repo_root).resolve()
    pkg_dir = Path(pkg_dir)
    language = resolve_output_language(default=language)
    symbols = symbols or load_symbol_index_jsonl(repo_root / "captures" / "symbol_index.jsonl")

    llm = create_llm_from_env(model_override=llm_model)

    docs_summary = truncate_text(_read_repo_docs_summary(repo_root), 8000)
    docs_summary = redact_text(docs_summary, redact_urls=False)

    for skill_dir in list_skill_dirs(pkg_dir):
        spec_path = skill_dir / "skillspec.json"
        skill_md_path = skill_dir / "skill.md"
        lib_path = skill_dir / "library.md"
        ref_dir = skill_dir / "reference"
        if not spec_path.exists():
            raise RuntimeError(f"Missing skillspec.json: {spec_path}")
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:
            raise RuntimeError(f"Invalid JSON in skillspec.json: {spec_path}")

        code_snippets = _code_snippets_from_evidence(repo_root, spec)
        for sn in code_snippets:
            if isinstance(sn, dict) and isinstance(sn.get("code"), str):
                sn["code"] = redact_text(sn["code"], redact_urls=False)
        run_logs = ""
        try:
            run_logs_path = repo_root / "captures" / "run_index.jsonl"
            if run_logs_path.exists():
                run_logs = redact_text(run_logs_path.read_text(encoding="utf-8")[:2000], redact_urls=False)
        except Exception:
            pass

        messages = make_repo_tutorial_prompt(
            language=language,
            spec=spec,
            code_snippets=code_snippets,
            docs_summary=docs_summary,
            run_logs=run_logs,
        )

        llm_out: dict[str, Any] = {}
        last_err: Exception | None = None
        base_messages = list(messages)
        # Model outputs may occasionally omit required keys; we retry with explicit feedback (still LLM-only).
        for attempt in range(1, 4):
            attempt_msg_dicts = [
                m.to_dict() if hasattr(m, "to_dict") else {"role": "unknown", "content": str(m)} for m in messages
            ]
            attempt_extra = {
                "skill_dir": skill_dir.as_posix(),
                "llm_provider": getattr(llm, "provider", ""),
                "llm_model": getattr(llm, "model", ""),
                "timeout_ms": int(timeout_ms or 300_000),
                "attempt": attempt,
            }
            try:
                llm_out = llm.chat_json(messages=messages, temperature=0.0, timeout_ms=int(timeout_ms or 300_000))
                write_llm_trace(repo_root, kind="rewrite.tutorial", messages=attempt_msg_dicts, response_obj=llm_out, extra=attempt_extra)
            except Exception as e:
                last_err = e
                write_llm_trace(
                    repo_root,
                    kind="rewrite.tutorial",
                    messages=attempt_msg_dicts,
                    response_obj={"error": str(e), "error_type": type(e).__name__},
                    extra=attempt_extra,
                )
                raise RuntimeError(f"LLM rewrite failed for skill dir: {skill_dir}") from e

            # Persist prompt + raw LLM reply for audit (per-attempt overwrite is OK; llm_traces keeps history).
            write_json_atomic(skill_dir / "llm_prompt.json", redact_obj({"messages": attempt_msg_dicts}, redact_urls=False))
            write_json_atomic(skill_dir / "llm_output.json", redact_obj(llm_out, redact_urls=False))

            issues: list[str] = []
            skill_md_new = str(llm_out.get("skill_md") or "").strip()
            library_md_new = str(llm_out.get("library_md") or "").strip()
            ref_new = llm_out.get("reference") if isinstance(llm_out.get("reference"), dict) else {}

            if not skill_md_new:
                issues.append("missing skill_md")
            if not library_md_new:
                issues.append("missing library_md")
            required_ref_keys = ["sources_md", "troubleshooting_md", "edge_cases_md", "examples_md", "changelog_md"]
            if not isinstance(ref_new, dict) or any(k not in ref_new for k in required_ref_keys):
                missing = [k for k in required_ref_keys if k not in (ref_new or {})]
                issues.append(f"missing reference keys: {missing}")

            if not issues:
                # Re-run the stricter local checks (same as validate rules).
                skill_issues = lint_skill_markdown(skill_md_new)
                if skill_issues:
                    issues.extend([f"skill.md: {x}" for x in skill_issues[:10]])
                if count_fenced_code_blocks(library_md_new) < 1:
                    issues.append("library.md: missing fenced code block")
                if find_raw_urls(library_md_new):
                    issues.append("library.md: raw URLs found")

                ref_text = {k: str(ref_new.get(k) or "").strip() for k in required_ref_keys}
                empty = [k for k, v in ref_text.items() if not v]
                if empty:
                    issues.append(f"reference empty: {empty}")
                if ref_text.get("examples_md") and count_fenced_code_blocks(ref_text["examples_md"]) < 1:
                    issues.append("examples_md: missing fenced code block")
                if ref_text.get("examples_md") and find_raw_urls(ref_text["examples_md"]):
                    issues.append("examples_md: raw URLs found")

                source_url = str(spec.get("source_url") or "").strip()
                expected_access = str(spec.get("source_fetched_at") or spec.get("generated_at") or "").strip()
                if source_url and source_url not in ref_text.get("sources_md", ""):
                    issues.append("sources_md: missing source_url")
                if expected_access and expected_access not in ref_text.get("sources_md", ""):
                    issues.append("sources_md: missing source_fetched_at")

                banned_schemes = ("http://", "https://", "file://")
                if any(s in skill_md_new for s in banned_schemes):
                    issues.append("skill_md: contains URL scheme")
                if any(s in library_md_new for s in banned_schemes):
                    issues.append("library_md: contains URL scheme")
                for k in ["troubleshooting_md", "edge_cases_md", "examples_md", "changelog_md"]:
                    if any(s in ref_text.get(k, "") for s in banned_schemes):
                        issues.append(f"{k}: contains URL scheme")
                # sources.md: allow exactly one primary URL.
                if source_url.startswith("file://"):
                    file_urls = re.findall(r"file://\S+", ref_text.get("sources_md", ""))
                    if file_urls != [source_url]:
                        issues.append("sources_md: non-primary file:// URL present")
                    if find_raw_urls(ref_text.get("sources_md", "")):
                        issues.append("sources_md: unexpected http(s) URL present")
                elif source_url.startswith("http://") or source_url.startswith("https://"):
                    urls = find_raw_urls(ref_text.get("sources_md", ""))
                    if urls != [source_url]:
                        issues.append("sources_md: non-primary http(s) URL present")

            if not issues:
                break

            # Retry with explicit feedback.
            feedback = {
                "attempt": attempt,
                "issues": issues[:50],
                "rules": "Follow the system instructions exactly. Output a complete JSON object; do not include URL schemes; include library_md and all reference.* fields.",
                "previous_output_preview": truncate_text(json.dumps(llm_out, ensure_ascii=False), 2500),
            }
            messages = base_messages + [
                ChatMessage(
                    role="user",
                    content="The previous output failed local validation. Return only the corrected full JSON (no explanations, no extra fields).\n"
                    + json.dumps(feedback, ensure_ascii=False, indent=2),
                )
            ]
        else:
            raise RuntimeError(f"LLM rewrite failed to produce valid output after retries for: {skill_dir}") from last_err

        # Final validated payload (after retry loop).
        skill_md_new = str(llm_out.get("skill_md") or "").strip()
        library_md_new = str(llm_out.get("library_md") or "").strip()
        ref_new = llm_out.get("reference") if isinstance(llm_out.get("reference"), dict) else {}
        required_ref_keys = ["sources_md", "troubleshooting_md", "edge_cases_md", "examples_md", "changelog_md"]
        ref_text = {k: str(ref_new.get(k) or "").strip() for k in required_ref_keys}

        write_text_atomic(skill_md_path, skill_md_new + "\n")
        write_text_atomic(lib_path, library_md_new + "\n")

        ref_dir.mkdir(parents=True, exist_ok=True)
        write_text_atomic(ref_dir / "sources.md", ref_text["sources_md"] + "\n")
        write_text_atomic(ref_dir / "troubleshooting.md", ref_text["troubleshooting_md"] + "\n")
        write_text_atomic(ref_dir / "edge-cases.md", ref_text["edge_cases_md"] + "\n")
        write_text_atomic(ref_dir / "examples.md", ref_text["examples_md"] + "\n")
        write_text_atomic(ref_dir / "changelog.md", ref_text["changelog_md"] + "\n")
