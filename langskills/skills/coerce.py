from __future__ import annotations

import json
from typing import Any


def coerce_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join("" if v is None else str(v) for v in value).strip()
    if isinstance(value, dict):
        for k in ("title", "text", "content", "value"):
            if isinstance(value.get(k), str):
                return value[k]
    return ""


def coerce_markdown(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for x in value:
            if isinstance(x, str):
                parts.append(x)
            elif x is None:
                continue
            else:
                parts.append(json.dumps(x, ensure_ascii=False))
        return "\n".join(p for p in parts if p).strip()
    if isinstance(value, dict):
        for k in ("markdown", "md", "content", "text", "value"):
            if isinstance(value.get(k), str):
                return value[k]
    return ""

