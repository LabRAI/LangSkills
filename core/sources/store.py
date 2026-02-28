from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.fs import ensure_dir, relpath_posix, write_json_atomic, write_text_atomic
from ..utils.hashing import sha256_hex
from ..utils.text import truncate_text


def global_sources_root(repo_root: str | Path) -> Path:
    return Path(repo_root) / "sources" / "by-id"


def write_global_source_from_artifact(
    *, repo_root: str | Path, artifact: dict[str, Any], artifact_path: Path | None = None, overwrite: bool = True
) -> Path | None:
    source_id = str(artifact.get("source_id") or "").strip()
    if not source_id:
        return None

    repo_root = Path(repo_root).resolve()
    dest_dir = global_sources_root(repo_root) / source_id
    if dest_dir.exists() and not overwrite:
        return dest_dir

    ensure_dir(dest_dir)

    source_url = str(artifact.get("url") or artifact.get("source_url") or "").strip()
    fetched_at = str(artifact.get("fetched_at") or "").strip()
    raw_excerpt = str(artifact.get("raw_excerpt") or "")
    extracted_text = str(artifact.get("extracted_text") or "")
    if not extracted_text and raw_excerpt:
        extracted_text = raw_excerpt

    raw_sha = sha256_hex(raw_excerpt) if raw_excerpt else ""
    extracted_sha = sha256_hex(extracted_text) if extracted_text else ""

    pointer: dict[str, Any] = {}
    if artifact_path:
        pointer["artifact_path"] = relpath_posix(artifact_path, repo_root)
    if source_url:
        pointer["source_url"] = source_url
    if raw_sha:
        pointer["raw_excerpt_sha256"] = raw_sha
    if extracted_sha:
        pointer["extracted_text_sha256"] = extracted_sha
    write_json_atomic(dest_dir / "raw_pointer.json", pointer)

    excerpt = truncate_text(extracted_text, 8000)
    if excerpt:
        write_text_atomic(dest_dir / "excerpt.txt", excerpt.rstrip() + "\n")

    fingerprint = artifact.get("fingerprint") if isinstance(artifact.get("fingerprint"), dict) else None
    if fingerprint:
        write_json_atomic(dest_dir / "fingerprint.json", fingerprint)

    src_meta = {
        "schema_version": 1,
        "source_id": source_id,
        "source_type": str(artifact.get("source_type") or ""),
        "source_url": source_url,
        "title": str(artifact.get("title") or ""),
        "fetched_at": fetched_at,
        "license_spdx": str(artifact.get("license_spdx") or ""),
        "license_risk": str(artifact.get("license_risk") or ""),
        "extra": artifact.get("extra") if isinstance(artifact.get("extra"), dict) else {},
        "artifact_path": relpath_posix(artifact_path, repo_root) if artifact_path else "",
        "raw_excerpt_sha256": raw_sha,
        "extracted_text_sha256": extracted_sha,
    }
    write_json_atomic(dest_dir / "source.json", src_meta)
    return dest_dir

