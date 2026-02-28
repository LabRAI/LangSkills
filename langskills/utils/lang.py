from __future__ import annotations

import os


def resolve_output_language(*, default: str = "en") -> str:
    raw = str(os.environ.get("LANGSKILLS_OUTPUT_LANGUAGE") or "").strip()
    if raw:
        return raw
    fallback = str(default or "").strip()
    return fallback or "en"
