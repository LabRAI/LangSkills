from __future__ import annotations

import json


def parse_metadata_yaml_text(yaml_text: str) -> dict:
    text = str(yaml_text or "").replace("\r\n", "\n")
    out: dict = {}
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        idx = line.find(":")
        if idx <= 0:
            continue
        key = line[:idx].strip()
        raw_val = line[idx + 1 :].strip()
        if not key:
            continue
        try:
            out[key] = json.loads(raw_val)
        except Exception:
            out[key] = raw_val
    return out


def encode_yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


def write_metadata_yaml_text(meta: dict) -> str:
    m = dict(meta or {})
    lines: list[str] = []
    for k, v in m.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            encoded = ", ".join(json.dumps(str(x)) for x in v)
            lines.append(f"{k}: [{encoded}]")
        else:
            lines.append(f"{k}: {encode_yaml_scalar(v)}")
    return "\n".join(lines) + "\n"

