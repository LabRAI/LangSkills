from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url
from ..utils.fingerprint import build_fingerprint
from ..utils.fs import ensure_dir, write_json_atomic
from ..utils.hashing import sha256_hex
from ..utils.redact import redact_text
from ..utils.time import utc_now_iso_z
from ..utils.text import truncate_text
from .store import write_global_source_from_artifact


@dataclass(frozen=True)
class SourceArtifact:
    schema_version: int
    source_id: str
    source_type: str
    url: str
    title: str
    fetched_at: str
    license_spdx: str
    license_risk: str
    raw_excerpt: str
    extracted_text: str
    fingerprint: dict[str, Any]
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "url": self.url,
            "title": self.title,
            "fetched_at": self.fetched_at,
            "license_spdx": self.license_spdx,
            "license_risk": self.license_risk,
            "raw_excerpt": self.raw_excerpt,
            "extracted_text": self.extracted_text,
            "fingerprint": self.fingerprint,
            "extra": self.extra,
        }


def write_source_artifact(
    *,
    run_dir: str | Path,
    source_type: str,
    url: str,
    title: str,
    raw_text: str,
    extracted_text: str,
    license_spdx: str,
    license_risk: str,
    extra: dict[str, Any] | None = None,
) -> SourceArtifact:
    source_url_raw = str(url or "").strip()
    source_url = canonicalize_source_url(source_url_raw) or source_url_raw
    source_id = sha256_hex(source_url)
    out_dir = Path(run_dir) / "sources"
    ensure_dir(out_dir)

    redact_urls = str(os.environ.get("LANGSKILLS_REDACT_URLS") or "").strip() == "1"
    max_chars_raw = str(os.environ.get("LANGSKILLS_SOURCE_TEXT_MAX_CHARS") or "").strip()
    try:
        max_chars = int(max_chars_raw) if max_chars_raw else 30_000
    except Exception:
        max_chars = 30_000
    max_chars = max(1_000, min(200_000, int(max_chars)))

    extracted_for_fp = truncate_text(redact_text(str(extracted_text or ""), redact_urls=redact_urls), max_chars)
    fp = build_fingerprint(extracted_for_fp).to_dict()

    save_text_raw = str(os.environ.get("LANGSKILLS_SAVE_SOURCE_TEXT") or "").strip()
    save_text = True if save_text_raw == "" else (save_text_raw != "0")
    extracted = extracted_for_fp if save_text else ""
    raw_excerpt = truncate_text(redact_text(str(raw_text or ""), redact_urls=redact_urls), max_chars) if save_text else ""

    record = SourceArtifact(
        schema_version=1,
        source_id=source_id,
        source_type=str(source_type or "").strip(),
        url=source_url,
        title=str(title or "").strip(),
        fetched_at=utc_now_iso_z(),
        license_spdx=str(license_spdx or "").strip(),
        license_risk=str(license_risk or "").strip(),
        raw_excerpt=raw_excerpt,
        extracted_text=extracted,
        fingerprint=fp,
        extra=dict(extra or {}),
    )

    artifact_path = out_dir / f"{source_id}.json"
    write_json_atomic(artifact_path, record.to_dict())

    enable_global = str(os.environ.get("LANGSKILLS_GLOBAL_SOURCES") or "").strip()
    if enable_global == "" or enable_global != "0":
        try:
            repo_root = Path(run_dir).resolve().parents[1]
            write_global_source_from_artifact(
                repo_root=repo_root, artifact=record.to_dict(), artifact_path=artifact_path, overwrite=True
            )
        except Exception:
            pass
    return record
