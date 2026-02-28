from __future__ import annotations

import hashlib
import re


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def slugify(text: str, max_len: int = 48) -> str:
    raw = str(text or "")
    value = raw.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")

    if not value:
        return f"t-{sha256_hex(raw)[:10]}"
    if len(value) <= max_len:
        return value

    h = sha256_hex(value)[:8]
    prefix_len = max(1, max_len - (len(h) + 1))
    prefix = value[:prefix_len].rstrip("-")
    return f"{prefix}-{h}"[:max_len]

