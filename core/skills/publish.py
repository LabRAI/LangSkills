from __future__ import annotations

import datetime as _dt
import os
import shutil
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url, license_decision, read_license_policy
from ..utils.fs import ensure_dir, list_skill_dirs, read_json, read_text, write_json_atomic, write_text_atomic
from ..utils.hashing import sha256_hex
from ..utils.skill_id import compute_skill_id, normalize_skill_metadata
from ..utils.time import utc_now_iso_z
from ..utils.yaml_simple import parse_metadata_yaml_text, write_metadata_yaml_text
from .markdown_ops import ensure_evidence_section, ensure_sources_contain_url, rewrite_reference_sources_md, strip_raw_urls_outside_sources


def load_skills_index(repo_root: str | Path) -> dict[str, Any]:
    p = Path(repo_root) / "skills" / "index.json"
    default = {"schema_version": 2, "updated_at": utc_now_iso_z(), "items": []}
    if not p.exists():
        return default
    try:
        obj = __import__("json").loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(obj, dict) or not isinstance(obj.get("items"), list):
        return default

    def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
        src_id = str(raw.get("primary_source_id") or raw.get("source_id") or "").strip()
        skill_kind = str(raw.get("skill_kind") or raw.get("topic") or raw.get("source_type") or "unknown").strip()
        language = str(raw.get("language") or raw.get("lang") or "en").strip()
        skill_id = str(raw.get("skill_id") or "").strip()
        if not skill_id and src_id:
            skill_id = compute_skill_id(source_id=src_id, skill_kind=skill_kind, language=language)
        dir_path = str(raw.get("dir") or "").strip() or (f"skills/by-skill/{skill_id}" if skill_id else "")
        return {
            "source_id": src_id,
            "primary_source_id": src_id,
            "skill_id": skill_id,
            "skill_kind": skill_kind,
            "language": language,
            "domain": str(raw.get("domain") or raw.get("profile") or ""),
            "profile": str(raw.get("profile") or raw.get("domain") or ""),
            "source_type": str(raw.get("source_type") or ""),
            "source_url": str(raw.get("source_url") or ""),
            "title": str(raw.get("title") or ""),
            "overall_score": float(raw.get("overall_score") or 0),
            "dir": dir_path,
            "updated_at": str(raw.get("updated_at") or ""),
        }

    seen: dict[str, dict[str, Any]] = {}
    for it in obj.get("items") or []:
        if not isinstance(it, dict):
            continue
        norm = _normalize_item(it)
        key = norm.get("skill_id") or norm.get("dir") or norm.get("source_id")
        if not key:
            continue
        seen[key] = norm

    return {"schema_version": 2, "updated_at": obj.get("updated_at") or utc_now_iso_z(), "items": list(seen.values())}


def _copy_reference_dir(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_dir():
        return
    ensure_dir(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def publish_run_to_skills_library(*, repo_root: str | Path, run_dir: str | Path, overwrite: bool = False) -> dict[str, int]:
    run_skills_root = Path(run_dir) / "skills"
    run_sources_root = Path(run_dir) / "sources"
    if not run_skills_root.exists():
        return {"published": 0, "skipped": 0, "total": 0}

    policy = read_license_policy(repo_root)
    if not policy:
        return {"published": 0, "skipped": 0, "total": 0}
    allow_needs_review = str(os.environ.get("LANGSKILLS_PUBLISH_ALLOW_NEEDS_REVIEW") or "").strip() == "1"

    dest_root = Path(repo_root) / "skills"
    by_skill_root = dest_root / "by-skill"
    by_source_root = dest_root / "by-source"
    legacy_root = dest_root / "legacy"
    ensure_dir(dest_root)
    ensure_dir(by_skill_root)
    ensure_dir(by_source_root)
    write_legacy = str(os.environ.get("LANGSKILLS_PUBLISH_LEGACY_VIEW") or "").strip() == "1"

    skill_dirs = list_skill_dirs(run_skills_root)
    index = load_skills_index(repo_root)
    existing_items: list[dict[str, Any]] = index.get("items") if isinstance(index.get("items"), list) else []
    by_skill_id: dict[str, dict[str, Any]] = {
        str(it.get("skill_id") or it.get("dir") or it.get("source_id") or ""): it for it in existing_items if isinstance(it, dict)
    }

    min_score_raw = str(os.environ.get("LANGSKILLS_PUBLISH_MIN_SCORE") or "").strip()
    min_publish_score = float(min_score_raw) if min_score_raw else 3.0

    published = 0
    skipped = 0
    for skill_dir in skill_dirs:
        skill_path = skill_dir / "skill.md"
        meta_path = skill_dir / "metadata.yaml"
        if not skill_path.exists() or not meta_path.exists():
            continue

        meta = normalize_skill_metadata(parse_metadata_yaml_text(read_text(meta_path)))

        score = float(meta.get("overall_score") or 0)
        if score < min_publish_score:
            skipped += 1
            continue

        title = str(meta.get("title") or "")
        md_text = read_text(skill_path)
        _lower = (title + " " + md_text).lower()
        if _lower.count("not provided") >= 15 or _lower.count("unverified") >= 15:
            skipped += 1
            continue

        profile = str(meta.get("profile") or meta.get("domain") or "").strip()
        domain = str(meta.get("domain") or profile or "").strip()
        source_type = str(meta.get("source_type") or "").strip()
        source_url_raw = str(meta.get("source_url") or "").strip()
        source_url = canonicalize_source_url(source_url_raw) or source_url_raw
        if not (source_type and source_url):
            continue

        spdx = str(meta.get("license_spdx") or "").strip()
        decision = license_decision(policy, source_type=source_type, license_spdx=spdx)
        if decision == "deny":
            skipped += 1
            continue

        skill_kind = str(meta.get("skill_kind") or meta.get("topic") or source_type or "unknown").strip()
        language = str(meta.get("language") or meta.get("lang") or "en").strip()
        source_id = sha256_hex(source_url)
        skill_id = compute_skill_id(source_id=source_id, skill_kind=skill_kind, language=language)
        dest_dir = by_skill_root / skill_id

        existing_meta_path = dest_dir / "metadata.yaml"
        should_write = bool(overwrite) or not existing_meta_path.exists()
        if not should_write:
            try:
                existing_meta = parse_metadata_yaml_text(read_text(existing_meta_path))
                old_score = float(existing_meta.get("overall_score") or 0)
                new_score = float(meta.get("overall_score") or 0)
                if new_score > old_score:
                    should_write = True
            except Exception:
                should_write = True

        if not should_write:
            skipped += 1
            continue

        # Resolve the best source artifact path (canonical first; then legacy ids).
        cand_ids: list[str] = []
        artifact_id = str(meta.get("source_artifact_id") or "").strip()
        if artifact_id:
            cand_ids.append(artifact_id)
        cand_ids.append(source_id)
        if source_url_raw and source_url_raw != source_url:
            cand_ids.append(sha256_hex(source_url_raw))
        cand_ids = [x for x in dict.fromkeys(cand_ids) if x]

        src_artifact_path: Path | None = None
        for cid in cand_ids:
            p = run_sources_root / f"{cid}.json"
            if p.exists():
                src_artifact_path = p
                break

        if src_artifact_path is None:
            skipped += 1
            continue

        src_obj = read_json(src_artifact_path, default={})
        if not isinstance(src_obj, dict):
            skipped += 1
            continue

        # Apply license gating using the resolved artifact when available.
        spdx_from_artifact = str(src_obj.get("license_spdx") or "").strip()
        spdx_eff = spdx or spdx_from_artifact
        decision = license_decision(policy, source_type=source_type, license_spdx=spdx_eff)
        if decision == "deny" or (decision == "needs_review" and not allow_needs_review):
            skipped += 1
            continue

        ensure_dir(dest_dir)

        # Normalize and publish skill.md with stable Evidence + Sources.
        md = read_text(skill_path)
        md = ensure_sources_contain_url(md, source_url)
        run_id = Path(run_dir).name
        artifact_ptr = f"captures/{run_id}/sources/{str(meta.get('source_artifact_id') or source_id).strip() or source_id}.json"
        published_ptr = f"skills/by-skill/{skill_id}/source.json:1"
        evidence_lines = [
            f"- run_id: {run_id}",
            f"- source_artifact: {artifact_ptr}",
            f"- published_source: {published_ptr}",
        ]
        md = ensure_evidence_section(md, evidence_lines)
        md = strip_raw_urls_outside_sources(md)
        write_text_atomic(dest_dir / "skill.md", md)

        lib_path = skill_dir / "library.md"
        if lib_path.exists():
            shutil.copy2(lib_path, dest_dir / "library.md")

        ref_dir = skill_dir / "reference"
        _copy_reference_dir(ref_dir, dest_dir / "reference")

        # Normalize url/source_id fields inside the published source.json.
        if isinstance(src_obj, dict):
            src_obj["source_id"] = source_id
            src_obj["url"] = source_url
        write_json_atomic(dest_dir / "source.json", src_obj)

        write_text_atomic(dest_dir / "published_at.txt", utc_now_iso_z() + "\n")
        write_text_atomic(dest_dir / "origin_run.txt", Path(run_dir).name + "\n")

        # Normalize metadata.yaml for canonical URL + artifact id (for future tooling).
        meta_out = dict(meta)
        meta_out["domain"] = domain
        meta_out["profile"] = profile
        meta_out["source_url"] = source_url
        meta_out["source_artifact_id"] = source_id
        meta_out["primary_source_id"] = source_id
        meta_out["skill_id"] = skill_id
        meta_out["skill_kind"] = skill_kind
        meta_out["language"] = language
        if not meta_out.get("source_refs"):
            meta_out["source_refs"] = [{"source_id": source_id, "source_type": source_type, "source_url": source_url}]
        write_text_atomic(dest_dir / "metadata.yaml", write_metadata_yaml_text(meta_out))

        # Normalize reference/sources.md to contain the canonical primary URL.
        rewrite_reference_sources_md(path=dest_dir / "reference" / "sources.md", source_url=source_url)

        # Optional legacy mirror (kept out of the primary index).
        if write_legacy and domain:
            legacy_dir = legacy_root / domain / source_type / source_id
            ensure_dir(legacy_dir)
            shutil.copytree(dest_dir, legacy_dir, dirs_exist_ok=True)

        item = {
            "source_id": source_id,
            "primary_source_id": source_id,
            "domain": domain,
            "profile": profile,
            "source_type": source_type,
            "source_url": source_url,
            "title": str(meta.get("title") or ""),
            "overall_score": float(meta.get("overall_score") or 0),
            "dir": dest_dir.relative_to(Path(repo_root)).as_posix(),
            "updated_at": utc_now_iso_z(),
            "skill_id": skill_id,
            "skill_kind": skill_kind,
            "language": language,
        }
        by_skill_id[skill_id or source_id] = item
        published += 1

        # lineage.json lives in by-skill (primary view)
        lineage_path = dest_dir / "lineage.json"
        if not lineage_path.exists():
            write_json_atomic(
                lineage_path,
                {
                    "schema_version": 1,
                    "skill_id": skill_id,
                    "generated_from": {
                        "primary_source_id": source_id,
                        "source_refs": [
                            {"source_id": source_id, "source_url": source_url, "source_type": source_type}
                        ],
                    },
                    "provenance": {
                        "run_id": run_id,
                        "pipeline": "publish",
                        "timestamp": utc_now_iso_z(),
                    },
                    "parents": [],
                },
            )

        # by-source view (reverse index)
        bs_dir = by_source_root / source_id
        ensure_dir(bs_dir)
        write_json_atomic(
            bs_dir / "source_ref.json",
            {
                "source_id": source_id,
                "source_url": source_url,
                "source_type": source_type,
                "skills": [skill_id] if skill_id else [],
                "updated_at": utc_now_iso_z(),
            },
        )
        skills_json = []
        skills_json_path = bs_dir / "skills.json"
        if skills_json_path.exists():
            try:
                skills_json = __import__("json").loads(skills_json_path.read_text(encoding="utf-8"))
            except Exception:
                skills_json = []
        if skill_id and skill_id not in skills_json:
            skills_json.append(skill_id)
        write_json_atomic(bs_dir / "skills.json", skills_json)

    items = sorted(by_skill_id.values(), key=lambda it: str(it.get("dir") or it.get("skill_id") or ""))
    index = {"schema_version": 2, "items": items, "updated_at": utc_now_iso_z()}
    write_json_atomic(dest_root / "index.json", index)

    return {"published": published, "skipped": skipped, "total": len(skill_dirs)}
