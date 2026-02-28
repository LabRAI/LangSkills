from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url
from ..skills.markdown_ops import ensure_evidence_section, rewrite_reference_sources_md
from ..utils.fs import ensure_dir, list_skill_dirs, read_json, read_text, rmrf, write_json_atomic, write_text_atomic
from ..utils.hashing import sha256_hex
from ..utils.skill_id import compute_skill_id, normalize_skill_metadata
from ..utils.time import utc_now_iso_z
from ..utils.yaml_simple import parse_metadata_yaml_text, write_metadata_yaml_text


def _float_or(meta: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(meta.get(key) or default)
    except Exception:
        return float(default)


def _published_at_key(skill_dir: Path) -> str:
    p = skill_dir / "published_at.txt"
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _ensure_evidence(*, path: Path, run_id: str, published_source_ptr: str) -> None:
    md = read_text(path)
    lines: list[str] = []
    rid = str(run_id or "").strip()
    if rid:
        lines.append(f"- run_id: {rid}")
    if published_source_ptr:
        lines.append(f"- published_source: {published_source_ptr}")
    if not lines:
        return
    out = ensure_evidence_section(md, lines)
    if out != md:
        write_text_atomic(path, out)


def _canonicalize_skill_dir(*, repo_root: Path, skill_dir: Path) -> tuple[Path, dict[str, Any], str, str]:
    meta_path = skill_dir / "metadata.yaml"
    meta = normalize_skill_metadata(parse_metadata_yaml_text(read_text(meta_path)) if meta_path.exists() else {})

    domain = str(meta.get("domain") or "").strip()
    source_type = str(meta.get("source_type") or "").strip()
    raw_url = str(meta.get("source_url") or "").strip()
    canon_url = canonicalize_source_url(raw_url) or raw_url
    source_id = sha256_hex(canon_url) if canon_url else skill_dir.name
    dest_dir = (repo_root / "skills" / domain / source_type / source_id) if (domain and source_type and canon_url) else skill_dir
    return dest_dir, meta, canon_url, raw_url


def normalize_library(*, repo_root: Path, root: Path, dry_run: bool) -> dict[str, int]:
    skill_dirs = [p for p in list_skill_dirs(root) if "by-skill" not in p.parts and "by-source" not in p.parts]
    if not skill_dirs:
        return {"total": 0, "moved": 0, "deduped": 0, "touched": 0}

    # Group by canonical destination dir.
    grouped: dict[Path, list[Path]] = {}
    meta_cache: dict[Path, dict[str, Any]] = {}
    url_cache: dict[Path, tuple[str, str]] = {}
    for d in skill_dirs:
        dest, meta, canon_url, raw_url = _canonicalize_skill_dir(repo_root=repo_root, skill_dir=d)
        grouped.setdefault(dest, []).append(d)
        meta_cache[d] = meta
        url_cache[d] = (canon_url, raw_url)

    moved = 0
    deduped = 0
    touched = 0

    # Resolve moves + de-dupe per canonical dest.
    for dest_dir, candidates in sorted(grouped.items(), key=lambda kv: str(kv[0])):
        ranked = []
        for d in candidates:
            meta = meta_cache.get(d, {})
            ranked.append(
                (
                    -_float_or(meta, "overall_score", 0.0),
                    _published_at_key(d),
                    str(d),
                )
            )
        keep = candidates[sorted(range(len(candidates)), key=lambda i: ranked[i])[0]]
        dupes = [d for d in candidates if d != keep]

        if dupes:
            deduped += len(dupes)

        if keep != dest_dir:
            if dry_run:
                print(f"DRY-RUN move: {keep} -> {dest_dir}")
            else:
                if dest_dir.exists() and dest_dir != keep:
                    rmrf(dest_dir)
                ensure_dir(dest_dir.parent)
                shutil.move(str(keep), str(dest_dir))
            moved += 1
        else:
            if not dry_run:
                ensure_dir(dest_dir)

        for d in dupes:
            if d == dest_dir:
                # When we move the kept dir into its canonical destination, `dest_dir` may also be
                # one of the duplicate candidates. Never delete the canonical destination after move.
                continue
            if dry_run:
                print(f"DRY-RUN rm: {d}")
            else:
                rmrf(d)

        # Normalize contents in the kept destination directory.
        final_dir = dest_dir
        meta_path = final_dir / "metadata.yaml"
        if not meta_path.exists():
            continue

        meta = parse_metadata_yaml_text(read_text(meta_path))
        domain = str(meta.get("domain") or "").strip()
        source_type = str(meta.get("source_type") or "").strip()
        raw_url = str(meta.get("source_url") or "").strip()
        canon_url = canonicalize_source_url(raw_url) or raw_url
        if not (domain and source_type and canon_url):
            continue

        source_id = sha256_hex(canon_url)
        # Ensure path is correct even if metadata drifted.
        expected_dir = repo_root / "skills" / domain / source_type / source_id
        if expected_dir != final_dir:
            if dry_run:
                print(f"DRY-RUN move(meta): {final_dir} -> {expected_dir}")
            else:
                if expected_dir.exists():
                    rmrf(expected_dir)
                ensure_dir(expected_dir.parent)
                shutil.move(str(final_dir), str(expected_dir))
            final_dir = expected_dir

        # metadata.yaml: canonical URL + artifact id.
        meta["source_url"] = canon_url
        meta["source_artifact_id"] = source_id
        if not dry_run:
            write_text_atomic(final_dir / "metadata.yaml", write_metadata_yaml_text(meta))

        # source.json: canonical URL + id.
        src_path = final_dir / "source.json"
        if src_path.exists():
            src = read_json(src_path, default={})
            if isinstance(src, dict):
                src["source_id"] = source_id
                src["url"] = canon_url
                if not dry_run:
                    write_json_atomic(src_path, src)

        # reference/sources.md: primary URL must match canonical URL.
        rewrite_reference_sources_md(path=final_dir / "reference" / "sources.md", source_url=canon_url)

        # skill.md: backfill Evidence pointers (no raw URLs).
        run_id = ""
        try:
            run_id = (final_dir / "origin_run.txt").read_text(encoding="utf-8").strip()
        except Exception:
            run_id = ""
        rel = final_dir.relative_to(repo_root).as_posix()
        published_ptr = f"{rel}/source.json:1"
        _ensure_evidence(path=final_dir / "skill.md", run_id=run_id, published_source_ptr=published_ptr)

        touched += 1

    # Rebuild skills/index.json (schema v2) and by-source reverse index from by-skill view.
    if not dry_run:
        by_skill_root = root / "by-skill"
        by_source_root = root / "by-source"
        ensure_dir(by_skill_root)
        ensure_dir(by_source_root)

        for d in list_skill_dirs(by_skill_root):
            meta_path = d / "metadata.yaml"
            if not meta_path.exists():
                continue
            meta = normalize_skill_metadata(parse_metadata_yaml_text(read_text(meta_path)))
            source_type = str(meta.get("source_type") or "").strip()
            source_url = str(meta.get("source_url") or "").strip()
            if not (source_type and source_url):
                continue
            primary_source_id = str(meta.get("primary_source_id") or meta.get("source_artifact_id") or "").strip()
            if not primary_source_id:
                primary_source_id = sha256_hex(source_url)
            skill_kind = str(meta.get("skill_kind") or meta.get("topic") or source_type or "unknown").strip()
            language = str(meta.get("language") or meta.get("lang") or "en").strip()
            skill_id = str(meta.get("skill_id") or compute_skill_id(source_id=primary_source_id, skill_kind=skill_kind, language=language) or "")

            bs_dir = by_source_root / primary_source_id
            ensure_dir(bs_dir)
            write_json_atomic(
                bs_dir / "source_ref.json",
                {
                    "source_id": primary_source_id,
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

        from .reindex_skills import build_index

        idx = build_index(repo_root=repo_root, root=by_skill_root)
        write_json_atomic(root / "index.json", idx)

    return {"total": len(skill_dirs), "moved": moved, "deduped": deduped, "touched": touched}


def cli_normalize_library(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills normalize-library")
    parser.add_argument("--root", default="skills")
    parser.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    root = Path(ns.root)
    if not root.is_absolute():
        root = (repo_root / root).resolve()

    out = normalize_library(repo_root=repo_root, root=root, dry_run=bool(ns.dry_run))
    print(
        f"OK: normalized {out['total']} skill dirs (moved={out['moved']} deduped={out['deduped']} touched={out['touched']})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_normalize_library())
