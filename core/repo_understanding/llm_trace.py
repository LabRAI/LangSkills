from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from ..utils.fs import write_json_atomic
from ..utils.hashing import sha256_hex
from ..utils.redact import redact_obj
from ..utils.time import utc_stamp_compact


def _normalize_messages(messages: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if hasattr(m, "to_dict") and callable(getattr(m, "to_dict")):
            try:
                out.append(m.to_dict())
                continue
            except Exception:
                pass
        if isinstance(m, dict):
            out.append(m)
            continue
        out.append({"content": str(m)})
    return out


def write_llm_trace(
    repo_root: Path,
    *,
    kind: str,
    messages: Iterable[Any],
    response_obj: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        out_dir = repo_root / "captures" / "llm_traces"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_stamp_compact()
        msg_dicts = _normalize_messages(messages)
        h = sha256_hex(json.dumps(msg_dicts, ensure_ascii=False))[:8]
        p = out_dir / f"{stamp}-{kind}-{h}.json"
        redact_urls = str(os.environ.get("LANGSKILLS_REDACT_URLS") or "").strip() == "1"
        write_json_atomic(
            p,
            redact_obj(
                {
                    "kind": kind,
                    "timestamp": stamp,
                    "messages": msg_dicts,
                    "response": response_obj,
                    "extra": extra or {},
                },
                redact_urls=redact_urls,
            ),
        )
    except Exception:
        return
