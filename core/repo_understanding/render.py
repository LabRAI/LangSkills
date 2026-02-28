from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.fingerprint import build_fingerprint
from ..utils.fs import ensure_dir, write_json_atomic, write_text_atomic
from ..utils.time import utc_now_iso_z
from ..utils.yaml_simple import write_metadata_yaml_text


def render_repo_skill_package_v2(*, out_dir: str | Path, spec: dict[str, Any]) -> Path:
    """
    Render a deterministic package-v2 style skill folder from a SkillSpec dict.

    This is intentionally LLM-free so it is reproducible and auditable.
    """
    out_dir = Path(out_dir)
    ensure_dir(out_dir)

    now = utc_now_iso_z()

    title = str(spec.get("name") or "Repo Skill").strip()
    goal = str(spec.get("goal") or "").strip()
    entrypoints = [str(x or "").strip() for x in (spec.get("entrypoints") or []) if str(x or "").strip()]
    steps = [str(x or "").strip() for x in (spec.get("steps") or []) if str(x or "").strip()]
    outputs = [str(x or "").strip() for x in (spec.get("outputs") or []) if str(x or "").strip()]
    failure_modes = [str(x or "").strip() for x in (spec.get("failure_modes") or []) if str(x or "").strip()]
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), list) else []

    source_url = str(spec.get("source_url") or "").strip()
    source_fetched_at = str(spec.get("source_fetched_at") or now).strip()
    source_type = str(spec.get("source_type") or "repo").strip() or "repo"
    license_spdx = str(spec.get("license_spdx") or "").strip()
    license_risk = str(spec.get("license_risk") or "unknown").strip() or "unknown"

    skill_md_lines: list[str] = []
    skill_md_lines.append(f"# {title}\n")
    if goal:
        skill_md_lines.append("## Goal")
        skill_md_lines.append(goal)
        skill_md_lines.append("")

    skill_md_lines.append("## Steps")
    if steps:
        for i, s in enumerate(steps, start=1):
            skill_md_lines.append(f"{i}. {s}")
    else:
        skill_md_lines.append("1. Review the repo entrypoints and commands.")
        skill_md_lines.append("2. Run the command and inspect artifacts.")
    skill_md_lines.append("")

    skill_md_lines.append("## Verification")
    cmd = entrypoints[0] if entrypoints else "echo \"OK\""
    skill_md_lines.append("```bash")
    skill_md_lines.append(cmd)
    skill_md_lines.append("```")
    skill_md_lines.append("")

    skill_md_lines.append("## Safety")
    skill_md_lines.append("- Do not commit secrets (API keys) into git; use `.env` and `.gitignore`.")
    skill_md_lines.append("")

    # Evidence is used for auditability (file:line pointers), and must not include raw URLs.
    skill_md_lines.append("## Evidence")
    if evidence:
        for ev in evidence[:10]:
            if not isinstance(ev, dict):
                continue
            p = str(ev.get("path") or "").strip()
            ln = int(ev.get("line") or 0) or 1
            if p:
                skill_md_lines.append(f"- {p}:{ln}")
    else:
        skill_md_lines.append("- (none)")
    skill_md_lines.append("")

    skill_md_lines.append("## Sources")
    if source_url:
        skill_md_lines.append(f"- {source_url}")
    for ev in evidence[:10]:
        if not isinstance(ev, dict):
            continue
        p = str(ev.get("path") or "").strip()
        ln = int(ev.get("line") or 0) or 1
        qn = str(ev.get("qualified_name") or "").strip()
        u = str(ev.get("url") or "").strip()
        if p:
            if qn:
                skill_md_lines.append(f"- {p}:{ln} (`{qn}`){f' — {u}' if u else ''}")
            else:
                skill_md_lines.append(f"- {p}:{ln}{f' — {u}' if u else ''}")
    skill_md_lines.append("")

    # Tutorial-style appendix for human-friendly reading.
    skill_md_lines.append("## Tutorial")
    skill_md_lines.append(
        "This section provides a more conversational walkthrough of the goal, setup, execution, and verification so a new contributor can follow it step-by-step."
    )
    skill_md_lines.append("")
    skill_md_lines.append("### Setup")
    skill_md_lines.append("- Activate the virtual environment: `source .venv/bin/activate` (or use your preferred Python environment).")
    if source_url:
        skill_md_lines.append(f"- Code source: {source_url}")
    skill_md_lines.append("- Ensure you have permission to write to `captures/`; generated artifacts will be stored there.")
    skill_md_lines.append("")
    skill_md_lines.append("### Step-by-step")
    if steps:
        for i, s in enumerate(steps, start=1):
            skill_md_lines.append(f"{i}. {s}")
    else:
        skill_md_lines.append("1. Read the skill entrypoints and understand required inputs.")
        skill_md_lines.append("2. Run the example command and inspect logs and `captures/` artifacts.")
    skill_md_lines.append("")
    skill_md_lines.append("### Verification and artifacts")
    skill_md_lines.append("- Run the Verification command below once to confirm dependencies and the environment are ready.")
    skill_md_lines.append("- Check that `captures/` contains `manifest.json` / `quality_report.json` / other expected artifacts.")
    skill_md_lines.append("- If there is a verification script or `validate` subcommand, it should complete without errors (strict mode will report missing fields).")
    skill_md_lines.append("")
    skill_md_lines.append("### Common failures")
    skill_md_lines.append("- Permission denied: if writes fail, check permissions for the working directory and `captures/`.")
    skill_md_lines.append("- Missing dependencies: ensure `.venv` has the dependencies from `requirements.txt` / `pyproject.toml` installed.")
    skill_md_lines.append("")

    skill_md = "\n".join(skill_md_lines).rstrip() + "\n"
    # Remove raw URLs outside Sources to satisfy validator.
    from ..skills.markdown_ops import strip_raw_urls_outside_sources

    skill_md = strip_raw_urls_outside_sources(skill_md)
    write_text_atomic(out_dir / "skill.md", skill_md)

    # library.md: no raw URLs, must include code block.
    lib_lines = [
        "# Library",
        "",
        "This skill documents a repo capability and how to exercise it via CLI.",
        "",
        "```bash",
        cmd,
        "```",
        "",
    ]
    write_text_atomic(out_dir / "library.md", "\n".join(lib_lines))

    ref_dir = out_dir / "reference"
    ensure_dir(ref_dir)

    sources_md = "\n".join(
        [
            "# Sources",
            "",
            f"- {source_url}" if source_url else "- (local repo)",
            "",
            f"Accessed at: {source_fetched_at}",
            "",
        ]
    )
    write_text_atomic(ref_dir / "sources.md", sources_md)

    troubleshooting_md = "\n".join(
        [
            "# Troubleshooting",
            "",
            "- If a command hangs, re-run with smaller counts (e.g. `@1`) and capture logs.",
            "- If the output is missing, inspect `captures/` and ensure directories are writable.",
            "",
        ]
    )
    write_text_atomic(ref_dir / "troubleshooting.md", troubleshooting_md)

    edge_cases_md = "\n".join(
        [
            "# Edge Cases",
            "",
            "- Running without `.venv` may use the wrong interpreter; prefer `./.venv/bin/python`.",
            "- Network-dependent steps may fail without credentials; set `LANGSKILLS_OFFLINE=1` when possible.",
            "",
        ]
    )
    write_text_atomic(ref_dir / "edge-cases.md", edge_cases_md)

    examples_md = "\n".join(
        [
            "# Examples",
            "",
            "```bash",
            cmd,
            "```",
            "",
        ]
    )
    write_text_atomic(ref_dir / "examples.md", examples_md)

    date = (spec.get("generated_at") or now)[:10]
    changelog_md = "\n".join(
        [
            "# Changelog",
            "",
            f"- **{date}**: initial package generation.",
            "",
        ]
    )
    write_text_atomic(ref_dir / "changelog.md", changelog_md)

    meta = {
        "id": str(spec.get("id") or "").strip() or str(out_dir.name),
        "title": title,
        "domain": str(spec.get("domain") or "devtools"),
        "topic": str(spec.get("topic") or "repo"),
        "slug": str(spec.get("slug") or out_dir.name),
        "source_type": source_type,
        "source_url": source_url,
        "source_fetched_at": source_fetched_at,
        "generated_at": now,
        "llm_provider": "repo-understanding",
        "llm_model": "",
        "prompt_sha256": "",
        "overall_score": 0,
        "source_artifact_id": "",
        "license_spdx": license_spdx,
        "license_risk": license_risk,
        "package_schema_version": 2,
        "package_generated_at": now,
        "package_llm_provider": "repo-understanding",
        "package_llm_model": "",
        "selection_source": str(spec.get("selection_source") or "rule"),
    }
    write_text_atomic(out_dir / "metadata.yaml", write_metadata_yaml_text(meta))

    source_text = "\n".join([goal, *steps, *outputs, *failure_modes]).strip()
    fp = build_fingerprint(source_text)
    source_obj = {
        "schema_version": 1,
        "source_type": source_type,
        "url": source_url,
        "title": title,
        "fetched_at": source_fetched_at,
        "raw_excerpt": "",
        "extracted_text": source_text,
        "fingerprint": fp.to_dict(),
        "license_spdx": license_spdx,
        "license_risk": license_risk,
        "extra": {
            "kind": "repo_skill",
            "spec_id": str(spec.get("id") or ""),
        },
    }
    write_json_atomic(out_dir / "source.json", source_obj)

    # Keep original spec for audit.
    write_json_atomic(out_dir / "skillspec.json", spec)
    return out_dir
