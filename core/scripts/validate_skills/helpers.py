"""Validation helper utilities."""
from __future__ import annotations

import re
from typing import Any

from ...utils.fingerprint import build_fingerprint
from ...utils.md import count_fenced_code_blocks, extract_section, find_raw_urls
from ...utils.text import normalize_for_fingerprint


def _has_url_placeholder(md: str | None = None) -> bool:
    return "<URL>" in str(md or "")


def _has_todo(md: str | None = None) -> bool:
    return bool(re.search(r"\bTODO\b", str(md or ""), flags=re.IGNORECASE))


def _find_primary_urls_for_sources_md(*, text: str | None, source_url: str | None) -> list[str] | None:
    src = str(source_url or "").strip()
    if src.startswith("file://"):
        return re.findall(r"file://\S+", str(text or ""))
    return find_raw_urls(str(text or ""))


_BANNED_MARKERS_RE = re.compile(
    r"\b(?:UNVERIFIED|FALLBACK_UNVERIFIED)\b", flags=re.IGNORECASE
)
_NOT_PROVIDED_RE = re.compile(r"\bnot\s+provided\b", flags=re.IGNORECASE)

_GENERIC_TOPIC_TAGS = {
    "cheat-sheet", "best-practices", "common-pitfalls", "command-patterns",
    "forensics-basics", "capacity-planning", "incident-response",
    "performance-tuning", "process-management", "hardening-checklist",
    "installation-and-setup", "os", "cli", "ops", "linux", "security",
    "automation", "filesystems", "fundamentals", "configuration", "troubleshooting",
}


def _normalize_match_text(text: str | None = None) -> str:
    parts = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return " ".join(parts)


def _derive_topic_terms_from_tags(meta: dict | None = None) -> list[str]:
    tags = meta.get("tags") if isinstance((meta or {}).get("tags"), list) else []
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        t = str(tag or "").strip().lower()
        if not t or t in seen or t in _GENERIC_TOPIC_TAGS:
            continue
        seen.add(t)
        out.append(t)
    return out


def _text_matches_topic_terms(*, text: str, terms: list[str]) -> bool:
    normalized = _normalize_match_text(text)
    for term in terms:
        t = _normalize_match_text(term)
        if t and t in normalized:
            return True
    return False


def _extract_fenced_code_block_bodies(md: str | None = None) -> list[str]:
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_fence = False
    buf: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^```", stripped):
            if in_fence:
                out.append("\n".join(buf))
                buf = []
                in_fence = False
            else:
                in_fence = True
            continue
        if in_fence:
            buf.append(line)
    return out


def _contains_not_provided_in_core_sections(md: str | None = None) -> bool:
    for name in ("Background", "Use Cases", "Inputs", "Outputs", "Steps", "Verification"):
        sec = extract_section(md, name)
        if sec and _NOT_PROVIDED_RE.search(str(sec)):
            return True
    return False


def _verification_has_non_placeholder_command(verification_section: str | None = None) -> bool:
    blocks = _extract_fenced_code_block_bodies(verification_section)
    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        for line in lines:
            if line.startswith("#"):
                continue
            if re.match(r"^echo\b.*;\s*exit\s+1$", line):
                continue
            if line and not line.startswith("echo"):
                return True
    return False


def plagiarism_check(
    *, skill_md: str, source_text: str, source_fingerprint: dict | None = None
) -> dict[str, Any]:
    if not source_text or not skill_md:
        return {"ratio": 0.0, "flagged": False}
    skill_norm = normalize_for_fingerprint(skill_md)
    source_norm = normalize_for_fingerprint(source_text)
    if not source_norm:
        return {"ratio": 0.0, "flagged": False}
    skill_tokens = set(skill_norm.split())
    source_tokens = set(source_norm.split())
    if not skill_tokens:
        return {"ratio": 0.0, "flagged": False}
    overlap = skill_tokens & source_tokens
    ratio = len(overlap) / len(skill_tokens) if skill_tokens else 0.0
    return {"ratio": round(ratio, 4), "flagged": ratio > 0.35}
