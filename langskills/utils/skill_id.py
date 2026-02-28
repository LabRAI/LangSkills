from __future__ import annotations

import json
from typing import Any

from .hashing import sha256_hex


def compute_skill_id(*, source_id: str, skill_kind: str | None = None, language: str | None = None) -> str:
    """
    Compute a stable skill_id.
    Default formula: sha256(source_id + ":" + skill_kind + ":" + language)
    """
    sid = (source_id or "").strip()
    if not sid:
        raise ValueError("source_id is required to compute skill_id.")
    kind = (skill_kind or "").strip()
    if not kind:
        raise ValueError("skill_kind is required to compute skill_id.")
    lang = (language or "").strip()
    if not lang:
        raise ValueError("language is required to compute skill_id.")
    return sha256_hex(f"{sid}:{kind}:{lang}")


def normalize_skill_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure common fields exist for downstream indexing.
    """
    m = dict(meta or {})
    m.setdefault("skill_kind", m.get("topic") or m.get("source_type") or "unknown")
    m.setdefault("language", m.get("lang") or "en")
    return m
