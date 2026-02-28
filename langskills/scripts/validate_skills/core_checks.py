"""Core validation checks for a single skill directory."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...config import canonicalize_source_url, license_decision
from ...utils.fs import find_nearest_sources_dir, read_json, read_text
from ...utils.hashing import sha256_hex
from ...utils.md import count_fenced_code_blocks, extract_section, find_raw_urls
from ...utils.time import iso_date_part
from ...utils.yaml_simple import parse_metadata_yaml_text
from .helpers import (
    _BANNED_MARKERS_RE,
    _contains_not_provided_in_core_sections,
    _derive_topic_terms_from_tags,
    _find_primary_urls_for_sources_md,
    _has_todo,
    _has_url_placeholder,
    _text_matches_topic_terms,
    _verification_has_non_placeholder_command,
    plagiarism_check,
)


def _is_git_lfs_pointer_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        head = path.read_bytes()[:64]
        return head.startswith(b"version https://git-lfs.github.com/spec/")
    except Exception:
        return False


def validate_skill_dir(
    *,
    d: Path,
    repo_root: Path,
    rel: str,
    policy: dict | None,
    strict: bool,
    check_package: bool,
    require_package_v2: bool = False,
    fail_on_lfs_pointer: bool = False,
    require_evidence: bool = True,
    require_skill_kind: bool = False,
    require_verification: bool = True,
    parse_source_json: bool = True,
    validate_topic_relevance: bool = False,
    validate_plagiarism: bool = False,
    min_code_blocks: int = 1,
    max_steps: int = 12,
    evidence_ptr_re: re.Pattern | None = None,
    errors: list[str],
    warnings: list[str],
) -> bool:
    """Validate a single skill directory. Returns False if the dir was skipped (LFS pointer)."""
    skill_path = d / "skill.md"
    meta_path = d / "metadata.yaml"
    src_path = d / "source.json"

    if _is_git_lfs_pointer_file(skill_path) or _is_git_lfs_pointer_file(meta_path):
        msg = f"{rel}: git-lfs pointer file detected; run `git lfs pull` for full validation"
        (errors if fail_on_lfs_pointer else warnings).append(msg)
        return False

    # Read skill markdown
    md = read_text(skill_path)
    if not md:
        errors.append(f"{rel}: skill.md is empty or missing")
        return True

    # Basic lint
    from ...utils.md import lint_skill_markdown
    lint = lint_skill_markdown(md)
    for it in lint:
        errors.append(f"{rel}: {it}")

    # Strict checks
    if strict:
        if _BANNED_MARKERS_RE.search(md):
            errors.append(f"{rel}: contains banned placeholders (UNVERIFIED/FALLBACK_UNVERIFIED)")
        if _contains_not_provided_in_core_sections(md):
            errors.append(f"{rel}: contains 'not provided' in core sections")

    # Code blocks
    if min_code_blocks > 0 and count_fenced_code_blocks(md) < min_code_blocks:
        errors.append(f"{rel}: skill.md missing fenced code blocks (min={min_code_blocks})")

    # Metadata
    meta_text = read_text(meta_path)
    meta = parse_metadata_yaml_text(meta_text) if meta_text else {}
    if not meta:
        warnings.append(f"{rel}: metadata.yaml missing or empty")

    # Source JSON
    src: dict = {}
    if parse_source_json and src_path.exists():
        src = read_json(src_path) or {}

    # Evidence check
    if require_evidence and strict:
        source_url = str(src.get("url") or meta.get("source_url") or "").strip()
        if not source_url:
            errors.append(f"{rel}: missing source URL (no evidence)")

    # Verification section
    if require_verification and strict:
        verification = extract_section(md, "Verification")
        if not verification:
            warnings.append(f"{rel}: missing Verification section")
        elif not _verification_has_non_placeholder_command(verification):
            warnings.append(f"{rel}: Verification section has no actionable commands")

    # License policy
    if policy and strict:
        source_type = str(src.get("source_type") or meta.get("source_type") or "").strip()
        license_spdx = str(src.get("license_spdx") or meta.get("license_spdx") or "").strip()
        decision = license_decision(policy, source_type=source_type, license_spdx=license_spdx)
        if decision == "deny":
            errors.append(f"{rel}: license denied ({license_spdx})")

    return True
