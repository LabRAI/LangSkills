from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any

from ..llm.types import ChatMessage, LlmClient
from ..skills.coerce import coerce_markdown
from ..skills.markdown_ops import (
    ensure_at_least_one_code_block,
    ensure_sources_contain_url,
    ensure_triad_sections,
    ensure_verification_has_code_block,
    extract_h2_section,
    remove_h2_section,
    strip_raw_urls_outside_sources,
)
from ..utils.fingerprint import build_fingerprint
from ..utils.fs import ensure_dir, read_text, resolve_run_dir, write_json_atomic, write_text_atomic
from ..utils.hashing import slugify
from ..utils.time import utc_now_iso_z
from ..utils.text import truncate_text
from ..utils.yaml_simple import write_metadata_yaml_text
from .dedupe import SkillFp, build_dedupe_clusters


def _flatten_domain_entry(domain_entry: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for k in ("web", "github", "forum"):
        arr = domain_entry.get(k) if isinstance(domain_entry.get(k), list) else []
        for s in arr:
            if isinstance(s, dict):
                out.append({"method": k, **s})
    return out


def make_matrix_and_combos_prompt(
    *,
    domain: str,
    skills: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    max_combos: int,
) -> list[ChatMessage]:
    max_n = max(0, min(5, int(max_combos or 3)))
    system = "\n".join(
        [
            "You are an expert skill library editor.",
            "You will analyze a batch of skills and produce:",
            "1) A role/framework/evaluation matrix per skill.",
            "2) 0..max_combos combo skills by MERGING the provided clusters (near-duplicates).",
            "",
            "Output ONLY a JSON object with keys: matrix, combo_skills.",
            "",
            "matrix must be an array with length = len(skills). Each item:",
            "{ id: string, title: string, roles: string[], frameworks_or_tools: string[], evaluation: string[] }",
            "- roles: e.g., Planner/ToolCaller/Critic/Operator/CI. If not applicable, use [].",
            "- frameworks_or_tools: key tool/framework names mentioned or implied. If none, use [].",
            "- evaluation: concrete verification signals or metrics (commands/assertions). If none, use [].",
            "",
            "combo_skills must be an array with length = min(max_combos, len(clusters)).",
            "Each item:",
            "{ idx:number, merged_ids: string[], title: string, skill_md: string }",
            "- merged_ids MUST equal exactly one cluster's skill_ids (do not invent ids).",
            "- skill_md MUST follow this exact markdown structure (English headings):",
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
            "- Must include at least 1 fenced code block ```...```.",
            "- Keep raw URLs in Sources; avoid raw URLs in prose. If a runnable snippet needs a URL, keep it inside fenced code blocks.",
            "- In Sources, include all source URLs from merged skills as bullet lines '- <url>'.",
        ]
    )
    user = json.dumps(
        {
            "domain": domain,
            "max_combos": max_n,
            "clusters": [{"idx": i + 1, "skill_ids": c.get("skill_ids", [])} for i, c in enumerate(clusters or [])],
            "skills": skills or [],
        },
        ensure_ascii=False,
        indent=2,
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def render_matrix_markdown(*, domain: str, matrix: list[dict[str, Any]]) -> str:
    rows = matrix or []
    lines: list[str] = []
    lines.append("# Role/Framework/Evaluation Matrix")
    lines.append("")
    lines.append(f"- Domain: {domain}")
    lines.append("")
    lines.append("| Skill ID | Title | Roles | Frameworks/Tools | Evaluation |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        rid = str(r.get("id") or "").replace("|", "\\|")
        title = str(r.get("title") or "").replace("|", "\\|")
        roles = ", ".join(str(x) for x in (r.get("roles") if isinstance(r.get("roles"), list) else [])).replace("|", "\\|")
        fw = ", ".join(str(x) for x in (r.get("frameworks_or_tools") if isinstance(r.get("frameworks_or_tools"), list) else [])).replace("|", "\\|")
        ev = ", ".join(str(x) for x in (r.get("evaluation") if isinstance(r.get("evaluation"), list) else [])).replace("|", "\\|")
        lines.append(f"| {rid} | {title} | {roles} | {fw} | {ev} |")
    lines.append("")
    return "\n".join(lines)


def postprocess_run(*, repo_root: str | Path, run_target: str, llm: LlmClient) -> dict[str, Any]:
    run_dir = resolve_run_dir(repo_root, run_target)
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in: {run_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    domains = manifest.get("domains") if isinstance(manifest.get("domains"), list) else []

    threshold = float(os.environ.get("LANGSKILLS_DEDUPE_THRESHOLD") or "0.25")
    max_combos = max(0, min(5, int(os.environ.get("LANGSKILLS_MAX_COMBOS") or "3")))

    analysis_root = Path(run_dir) / "analysis"
    ensure_dir(analysis_root)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "run_id": str(manifest.get("run_id") or Path(run_dir).name),
        "created_at": utc_now_iso_z(),
        "dedupe_threshold": threshold,
        "max_combos": max_combos,
        "domains": [],
        "errors": [],
    }

    report_lines: list[str] = []
    report_lines.append("# Postprocess Report")
    report_lines.append("")
    report_lines.append(f"- Run: {summary['run_id']}")
    report_lines.append(f"- Created at: {summary['created_at']}")
    report_lines.append(f"- Dedupe threshold: {summary['dedupe_threshold']}")
    report_lines.append(f"- Max combos: {summary['max_combos']}")
    report_lines.append("")

    for d in domains:
        if not isinstance(d, dict):
            continue
        domain = str(d.get("domain") or "").strip()
        if not domain:
            continue

        out_dir = analysis_root / domain
        ensure_dir(out_dir)

        skill_infos: list[dict[str, Any]] = []
        for s in _flatten_domain_entry(d):
            rel_dir = str(s.get("rel_dir") or "").strip()
            if not rel_dir:
                continue
            skill_path = Path(run_dir) / rel_dir / "skill.md"
            if not skill_path.exists():
                continue

            md = read_text(skill_path)
            md_no_sources = remove_h2_section(md, "Sources")
            fp = build_fingerprint(md_no_sources).to_dict()

            scenario = extract_h2_section(md, "Use Cases")
            inputs = extract_h2_section(md, "Inputs")
            outputs = extract_h2_section(md, "Outputs")
            steps = extract_h2_section(md, "Steps")
            step_lines = [line.strip() for line in steps.split("\n") if line.strip() and re.match(r"^\d+\.\s+", line.strip())][:3]

            skill_id = str(s.get("id") or "").strip()
            title = str(s.get("title") or "").strip()
            source_url = str(s.get("source_url") or "").strip()
            source_type = str(s.get("source_type") or s.get("method") or "").strip()

            card = {
                "id": skill_id,
                "title": title,
                "source_type": source_type,
                "source_url": source_url,
                "scenario": truncate_text(scenario, 800),
                "inputs": truncate_text(inputs, 900),
                "outputs": truncate_text(outputs, 900),
                "key_steps": step_lines,
            }
            skill_infos.append(
                {
                    "id": skill_id,
                    "title": title,
                    "source_type": source_type,
                    "source_url": source_url,
                    "rel_dir": rel_dir,
                    "fingerprint": fp,
                    "card": card,
                }
            )

        dedupe = build_dedupe_clusters(
            skills=[SkillFp(id=x["id"], title=x["title"], rel_dir=x["rel_dir"], fingerprint=x["fingerprint"]) for x in skill_infos],
            threshold=threshold,
        )

        clusters = [
            {
                "idx": idx + 1,
                "skill_ids": [s["id"] for s in group],
                "titles": [str(s.get("title") or "") for s in group],
            }
            for idx, group in enumerate(dedupe.get("clusters") or [])
            if isinstance(group, list)
        ]

        write_json_atomic(out_dir / "dedupe.json", dedupe)

        report_lines.append(f"## Domain: {domain}")
        report_lines.append("")
        report_lines.append(f"- Skills analyzed: {len(skill_infos)}")
        report_lines.append(f"- Dedupe clusters: {len(clusters)}")
        report_lines.append("")
        if clusters:
            report_lines.append("### Dedupe clusters")
            report_lines.append("")
            for c in clusters:
                report_lines.append(f"- C{c['idx']}: {', '.join(c['skill_ids'])}")
            report_lines.append("")

        dom_summary: dict[str, Any] = {
            "domain": domain,
            "skills": [
                {"id": x["id"], "title": x["title"], "rel_dir": x["rel_dir"], "source_url": x["source_url"], "source_type": x["source_type"]}
                for x in skill_infos
            ],
            "dedupe": dedupe,
            "clusters": clusters,
            "matrix": None,
            "combos": [],
            "errors": [],
        }

        if llm is not None:
            try:
                top_clusters = clusters[:max_combos]
                messages = make_matrix_and_combos_prompt(
                    domain=domain,
                    skills=[x["card"] for x in skill_infos],
                    clusters=top_clusters,
                    max_combos=max_combos,
                )
                out = llm.chat_json(messages=messages, temperature=0.2, timeout_ms=120_000)

                matrix = out.get("matrix") if isinstance(out, dict) else []
                matrix = matrix if isinstance(matrix, list) else []
                dom_summary["matrix"] = matrix
                write_json_atomic(out_dir / "matrix.json", {"domain": domain, "matrix": matrix})
                write_text_atomic(out_dir / "matrix.md", render_matrix_markdown(domain=domain, matrix=matrix) + "\n")

                combos = out.get("combo_skills") if isinstance(out, dict) else []
                combos = combos if isinstance(combos, list) else []
                combos_dir = out_dir / "combos"
                ensure_dir(combos_dir)

                combo_seq = 0
                for c0 in combos:
                    if not isinstance(c0, dict):
                        continue
                    merged = [str(x).strip() for x in (c0.get("merged_ids") if isinstance(c0.get("merged_ids"), list) else []) if str(x).strip()]
                    title = str(c0.get("title") or "").strip()
                    md = coerce_markdown(c0.get("skill_md"))
                    if not title or not md or len(md.strip()) < 50:
                        continue

                    urls = [str(next((x["source_url"] for x in skill_infos if x["id"] == mid), "")).strip() for mid in merged]
                    urls = [u for u in urls if u]

                    for u in urls:
                        md = ensure_sources_contain_url(md, u)
                    md = strip_raw_urls_outside_sources(md)
                    md = ensure_at_least_one_code_block(md)
                    md = ensure_verification_has_code_block(md)
                    md = ensure_triad_sections(md)

                    combo_seq += 1
                    combo_slug = f"c-{str(combo_seq).rjust(4, '0')}-{slugify(title, 40)}"
                    combo_rel_dir = Path("analysis") / domain / "combos" / combo_slug
                    combo_abs_dir = Path(run_dir) / combo_rel_dir
                    ensure_dir(combo_abs_dir)
                    write_text_atomic(combo_abs_dir / "skill.md", md)

                    combo_id = f"{domain}/combo/{combo_slug}"
                    meta = {
                        "id": combo_id,
                        "title": title,
                        "domain": domain,
                        "topic": "combo",
                        "slug": combo_slug,
                        "source_type": "combo",
                        "source_urls": urls,
                        "generated_at": utc_now_iso_z(),
                        "llm_provider": getattr(llm, "provider", ""),
                        "llm_model": getattr(llm, "model", ""),
                        "merged_ids": merged,
                    }
                    write_text_atomic(combo_abs_dir / "metadata.yaml", write_metadata_yaml_text(meta))
                    dom_summary["combos"].append(
                        {
                            "id": combo_id,
                            "title": title,
                            "rel_dir": combo_rel_dir.as_posix(),
                            "merged_ids": merged,
                            "source_urls": urls,
                        }
                    )
            except Exception as e:
                msg = str(e)
                dom_summary["errors"].append(msg)
                report_lines.append(f"- WARN: LLM postprocess failed: {msg}")
                report_lines.append("")

        summary["domains"].append(
            {
                "domain": domain,
                "skills_analyzed": len(skill_infos),
                "clusters": [{"idx": c["idx"], "skill_ids": c["skill_ids"]} for c in clusters],
                "combos": dom_summary["combos"],
                "errors": dom_summary["errors"],
            }
        )

    write_json_atomic(Path(run_dir) / "postprocess.json", summary)
    write_text_atomic(Path(run_dir) / "postprocess.md", "\n".join(report_lines) + "\n")
    return summary
