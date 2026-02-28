from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url, license_decision, read_license_policy
from ..utils.fs import list_skill_dirs, read_text
from ..utils.hashing import sha256_hex
from ..utils.md import count_fenced_code_blocks, extract_section, lint_skill_markdown
from ..utils.time import utc_now_iso_z
from ..utils.yaml_simple import parse_metadata_yaml_text


_EVIDENCE_PTR_RE = __import__("re").compile(
    r"(\b[\w./-]+\.(?:py|md|js|ts|go|rs|java|json|ya?ml|toml|cfg|ini):\d+\b"
    r"|\brun-\d{4}(?:-?\d{2}){2}-\d{6,9}Z(?:-[\\w-]{1,80})?\b"
    r"|captures/run-[^\\s/]+/manifest\\.json"
    r"|captures/run-[^\\s/]+/sources/[0-9a-f]{64}\\.json"
    r"|https?://github\\.com/[^\\s#]+#L\\d+)",
    flags=__import__("re").IGNORECASE,
)


def _parse_iso_date(iso: str) -> _dt.datetime | None:
    raw = str(iso or "").strip()
    if not raw:
        return None
    try:
        return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _freshness_days(iso: str) -> int | None:
    dt = _parse_iso_date(iso)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    return max(0, int((now - dt).total_seconds() // 86400))


def build_index(*, repo_root: Path, root: Path) -> dict[str, Any]:
    policy = read_license_policy(repo_root)
    items: list[dict[str, Any]] = []
    for d in list_skill_dirs(root):
        meta_path = d / "metadata.yaml"
        skill_path = d / "skill.md"
        if not meta_path.exists() or not skill_path.exists():
            continue
        meta = parse_metadata_yaml_text(meta_path.read_text(encoding="utf-8"))
        source_url = str(meta.get("source_url") or "").strip()
        if not source_url:
            continue
        canon_url = canonicalize_source_url(source_url) or source_url
        primary_source_id = (
            str(meta.get("primary_source_id") or meta.get("source_id") or meta.get("source_artifact_id") or "").strip()
            or sha256_hex(canon_url)
        )
        skill_kind = str(meta.get("skill_kind") or meta.get("topic") or meta.get("source_type") or "unknown").strip()
        language = str(meta.get("language") or meta.get("lang") or "en").strip()
        skill_id = str(meta.get("skill_id") or d.name or "").strip()

        skill_md = read_text(skill_path)
        lint_issues = lint_skill_markdown(skill_md)
        evidence = extract_section(skill_md, "Evidence")
        verification = extract_section(skill_md, "Verification")
        has_evidence = bool(evidence.strip()) and bool(_EVIDENCE_PTR_RE.search(evidence))
        verification_runnable = count_fenced_code_blocks(verification) > 0
        fetched_at = str(meta.get("source_fetched_at") or "")

        tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
        source_refs = meta.get("source_refs") if isinstance(meta.get("source_refs"), list) else []
        spdx = str(meta.get("license_spdx") or "").strip()
        source_type = str(meta.get("source_type") or "").strip()
        decision = license_decision(policy, source_type=source_type, license_spdx=spdx) if policy else ""

        items.append(
            {
                "source_id": primary_source_id,
                "primary_source_id": primary_source_id,
                "skill_id": skill_id,
                "skill_kind": skill_kind,
                "language": language,
                "domain": str(meta.get("domain") or meta.get("profile") or ""),
                "profile": str(meta.get("profile") or meta.get("domain") or ""),
                "source_type": source_type,
                "source_url": canon_url,
                "title": str(meta.get("title") or ""),
                "overall_score": float(meta.get("overall_score") or 0),
                "dir": d.relative_to(repo_root).as_posix(),
                "updated_at": utc_now_iso_z(),
                "lint_errors_count": len(lint_issues),
                "lint_warnings_count": 0,
                "has_evidence": has_evidence,
                "verification_runnable": verification_runnable,
                "license_decision": decision,
                "source_freshness_days": _freshness_days(fetched_at),
                "dedupe_cluster_id": str(meta.get("dedupe_cluster_id") or ""),
                "human_review_status": str(meta.get("human_review_status") or ""),
                "tags": tags,
                "source_refs": source_refs,
            }
        )
    items.sort(key=lambda it: str(it.get("dir") or ""))
    return {"schema_version": 2, "updated_at": utc_now_iso_z(), "items": items}


def cli_reindex_skills(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills reindex-skills")
    parser.add_argument("--root", default="skills/by-skill", help="Root dir to index (default: skills/by-skill)")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    root = Path(ns.root)
    if not root.is_absolute():
        root = repo_root / root
    if not root.exists():
        raise FileNotFoundError(f"Root not found: {root}")

    idx = build_index(repo_root=repo_root, root=root)
    out_path = repo_root / "skills" / "index.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.relative_to(repo_root)} with {len(idx['items'])} items")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_reindex_skills())
