from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..config import license_decision, read_license_policy
from ..repo_understanding.llm_candidate_selector import select_candidates_with_llm
from ..repo_understanding.license_detect import detect_repo_license_spdx
from ..repo_understanding.llm_writer import rewrite_repo_skills_with_llm
from ..repo_understanding.render import render_repo_skill_package_v2
from ..repo_understanding.skillspec import build_skillspecs_from_llm_candidates, write_skillspecs
from ..repo_understanding.symbol_index import load_symbol_index_jsonl
from ..scripts.repo_index import cli_repo_index as repo_index_main
from ..scripts.validate_skills import validate_skills
from ..env import load_dotenv
from ..utils.hashing import sha256_hex
from ..utils.lang import resolve_output_language
from ..utils.time import utc_stamp_compact
from ..utils.time import utc_now_iso_z


def cli_skill_from_repo(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills skill-from-repo")
    parser.add_argument("--target", choices=["cli", "workflow", "module", "troubleshooting"], default="cli")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--index", default="captures/symbol_index.jsonl")
    parser.add_argument("--spec-out", default="captures/skillspec")
    parser.add_argument("--pkg-out", default="captures/repo_skills")
    parser.add_argument("--validate", action="store_true", help="Run validate --strict --package on generated packages root")
    parser.add_argument("--llm", action="store_true", help="Use LLM to rewrite skills into tutorial style")
    parser.add_argument("--llm-model", default=str(os.environ.get("OPENAI_MODEL") or ""), help="LLM model name (optional)")
    parser.add_argument("--llm-candidates", action="store_true", help="Use LLM to pick skill candidates instead of rule-based scoring")
    parser.add_argument("--llm-dir-candidates", action="store_true", help="Use LLM to pick files then derive candidates")
    parser.add_argument("--llm-timeout-ms", type=int, default=300_000, help="LLM request timeout in ms (default: 300000)")
    parser.add_argument("--language", default="en", help="Language for LLM-generated content")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    # Ensure repo-local `.env` is loaded for skill-from-repo runs.
    load_dotenv(repo_root)

    if not ns.llm_candidates:
        raise RuntimeError("LLM-only build: pass --llm-candidates.")
    if not ns.llm_dir_candidates:
        raise RuntimeError("LLM-only build: pass --llm-dir-candidates (directory-based candidates).")
    if not ns.llm:
        raise RuntimeError("LLM-only build: pass --llm (tutorial rewrite).")

    # Ensure symbol index exists.
    idx = Path(ns.index)
    if not idx.is_absolute():
        idx = (repo_root / idx).resolve()
    if not idx.exists():
        repo_index_main([])

    symbols = load_symbol_index_jsonl(idx)
    # Prefer a relative index path in rendered SkillSpecs to avoid leaking absolute local paths.
    try:
        entry_index = idx.relative_to(repo_root).as_posix()
    except Exception:
        entry_index = idx.as_posix()

    run_id = f"run-{utc_stamp_compact()}-{sha256_hex('|'.join([entry_index, str(ns.target), str(ns.top), str(ns.llm_model), str(ns.llm_timeout_ms)]))[:8]}"

    docs_summary_parts: list[str] = []
    for p in [
        repo_root / "README.md",
        repo_root / "plan_githubagent.md",
        repo_root / "docs" / "repo_inventory.md",
        repo_root / "docs" / "verify_log.md",
    ]:
        if p.exists():
            try:
                docs_summary_parts.append(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    docs_summary = "\n\n".join(docs_summary_parts)

    output_language = resolve_output_language(default=str(ns.language or "en"))
    candidates = select_candidates_with_llm(
        repo_root=repo_root,
        symbols=symbols,
        target=str(ns.target or "cli"),
        top_n=int(ns.top or 10),
        language=output_language,
        docs_summary=docs_summary,
        max_symbols=max(60, int(ns.top or 10) * 8),
        llm_model=str(ns.llm_model or "").strip() or None,
        dir_based=True,
        index_dir=idx.parent,
        index_path=entry_index,
        timeout_ms=int(ns.llm_timeout_ms or 300_000),
    )
    specs = build_skillspecs_from_llm_candidates(
        repo_root=repo_root,
        symbols=symbols,
        candidates=candidates,
        target=str(ns.target or "cli"),
        index_path=entry_index,
    )
    if not specs:
        raise RuntimeError("No SkillSpecs were built from LLM candidates (unexpected).")

    policy = read_license_policy(repo_root)
    snapshot_root = idx.parent / "repo_snapshot"
    license_root = snapshot_root if snapshot_root.exists() else repo_root
    license_spdx = detect_repo_license_spdx(license_root)
    try:
        license_root_label = license_root.relative_to(repo_root).as_posix()
    except Exception:
        license_root_label = license_root.as_posix()
    for s in specs:
        s["license_spdx"] = license_spdx
        s["license_risk"] = license_decision(policy, source_type=str(s.get("source_type") or ""), license_spdx=license_spdx)

    for s in specs:
        if "selection_source" not in s:
            s["selection_source"] = "llm"

    spec_out_dir = Path(ns.spec_out)
    if not spec_out_dir.is_absolute():
        spec_out_dir = (repo_root / spec_out_dir).resolve()
    spec_out_dir = spec_out_dir / str(ns.target or "cli") / run_id
    written_specs = write_skillspecs(out_dir=spec_out_dir, specs=specs)

    pkg_out_dir = Path(ns.pkg_out)
    if not pkg_out_dir.is_absolute():
        pkg_out_dir = (repo_root / pkg_out_dir).resolve()
    pkg_out_dir = pkg_out_dir / str(ns.target or "cli") / run_id
    pkg_out_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[str] = []
    for s in specs:
        slug = str(s.get("slug") or "")
        if not slug:
            continue
        sid = str(s.get("id") or "")
        h = sha256_hex(sid)[:8] if sid else sha256_hex(slug)[:8]
        out_dir = pkg_out_dir / f"{slug}-{h}"
        render_repo_skill_package_v2(out_dir=out_dir, spec=s)
        rendered.append(out_dir.relative_to(repo_root).as_posix())

    rewrite_repo_skills_with_llm(
        repo_root=repo_root,
        pkg_dir=pkg_out_dir,
        language=output_language,
        llm_model=str(ns.llm_model or "").strip() or None,
        timeout_ms=int(ns.llm_timeout_ms or 300_000),
        symbols=symbols,
    )

    traceability_ratio = 0.0
    if specs:
        with_ev = sum(1 for s in specs if isinstance(s.get("evidence"), list) and s.get("evidence"))
        traceability_ratio = with_ev / len(specs)

    result = {
        "run_id": run_id,
        "target": str(ns.target or "cli"),
        "specs_written": len(written_specs),
        "packages_rendered": len(rendered),
        "spec_dir": str(spec_out_dir),
        "pkg_dir": str(pkg_out_dir),
        "index": entry_index,
        "traceability_ratio": traceability_ratio,
        "license_root": license_root_label,
        "license_spdx": license_spdx,
    }

    if ns.validate:
        errors, warnings = validate_skills(repo_root=repo_root, root=pkg_out_dir, strict=True, check_package=True)
        result["validate"] = {"errors": len(errors), "warnings": len(warnings)}
        if errors:
            # Persist failure evidence for audit / patch-loop workflows.
            try:
                patch_path = repo_root / "captures" / "patch_notes.jsonl"
                patch_path.parent.mkdir(parents=True, exist_ok=True)
                rec = {
                    "schema_version": 1,
                    "timestamp": utc_now_iso_z(),
                    "kind": "skill-from-repo.validate_fail",
                    "run_id": run_id,
                    "target": str(ns.target or "cli"),
                    "index": entry_index,
                    "spec_dir": str(spec_out_dir),
                    "pkg_dir": str(pkg_out_dir),
                    "errors": errors[:200],
                    "warnings": warnings[:200],
                    "suggested_next": f"./.venv/bin/python langskills_cli.py skill-from-repo --target {ns.target} --top {ns.top} --index {entry_index} --validate",
                }
                with patch_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass
            for e in errors[:20]:
                print(f"FAIL: {e}")
            return 1
        for w in warnings:
            print(f"WARN: {w}")

    # Metrics artifact (best-effort).
    try:
        from ..repo_understanding.metrics import update_metrics

        update_metrics(
            repo_root / "captures" / "metrics.json",
            section="skill_from_repo",
            data={
                "generated_at": utc_now_iso_z(),
                **result,
            },
        )
    except Exception:
        pass

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_skill_from_repo())
