from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.fs import write_json_atomic
from ..utils.time import utc_now_iso_z


def load_metrics(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"schema_version": 1, "updated_at": "", "sections": {}}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "updated_at": "", "sections": {}}
    if not isinstance(obj, dict):
        return {"schema_version": 1, "updated_at": "", "sections": {}}
    obj.setdefault("schema_version", 1)
    obj.setdefault("sections", {})
    return obj


def update_metrics(path: str | Path, *, section: str, data: dict[str, Any]) -> dict[str, Any]:
    p = Path(path)
    m = load_metrics(p)
    secs = m.get("sections")
    if not isinstance(secs, dict):
        secs = {}
        m["sections"] = secs
    secs[str(section)] = dict(data)
    m["updated_at"] = utc_now_iso_z()
    write_json_atomic(p, m)
    return m

