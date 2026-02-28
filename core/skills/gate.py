from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..env import env_bool, env_int
from ..llm.types import LlmClient
from ..utils.fs import ensure_dir, read_json, write_json_atomic
from ..utils.hashing import sha256_hex
from ..utils.redact import redact_obj
from ..utils.time import utc_now_iso_z
from ..utils.text import truncate_text
from .prompts import make_skill_gate_prompt


def _prompt_sha(messages: list) -> str:
    return sha256_hex(json.dumps([getattr(m, "to_dict")() for m in messages], ensure_ascii=False))


def _save_llm_artifacts_enabled() -> bool:
    raw = str(os.environ.get("LANGSKILLS_SAVE_LLM_ARTIFACTS") or "").strip()
    return True if raw == "" else (raw != "0")


def _allow_for_verdict(*, verdict: str, maybe_action: str, fail_open: bool) -> bool:
    v = str(verdict or "").strip().lower()
    if v == "pass":
        return True
    if v == "maybe":
        return str(maybe_action or "pass").strip().lower() != "skip"
    if v == "error":
        return bool(fail_open)
    return False


def run_skill_gate(
    *,
    run_dir: str | Path,
    domain: str,
    method: str,
    source_id: str,
    source_url: str,
    source_title: str,
    extracted_text: str,
    llm: LlmClient | None,
) -> dict[str, Any]:
    """
    LLM-based pre-filter before skill generation.

    Writes: captures/<run_id>/gates/<source_id>.json
    """
    enabled = env_bool("LANGSKILLS_ENABLE_SKILL_GATE", False)
    fail_open = env_bool("LANGSKILLS_SKILL_GATE_FAIL_OPEN", True)
    maybe_action = str(os.environ.get("LANGSKILLS_SKILL_GATE_MAYBE_ACTION") or "pass").strip().lower() or "pass"
    excerpt_chars = max(200, min(40_000, env_int("LANGSKILLS_SKILL_GATE_EXCERPT_CHARS", 4000)))
    timeout_ms = max(5_000, min(300_000, env_int("LANGSKILLS_SKILL_GATE_TIMEOUT_MS", 30_000)))

    run_dir = Path(run_dir)
    run_id = run_dir.name
    sid = str(source_id or "").strip() or sha256_hex(str(source_url or "").strip())
    url = str(source_url or "").strip()
    title = str(source_title or "").strip()

    excerpt = truncate_text(str(extracted_text or "").strip(), excerpt_chars)
    text_hash = sha256_hex(excerpt)

    gate_dir = run_dir / "gates"
    ensure_dir(gate_dir)
    gate_path = gate_dir / f"{sid}.json"

    def _summarize(saved: dict[str, Any], *, cached: bool) -> dict[str, Any]:
        verdict = str(saved.get("verdict") or "").strip().lower()
        allow = _allow_for_verdict(verdict=verdict, maybe_action=maybe_action, fail_open=fail_open)
        return {
            "enabled": bool(enabled),
            "cached": bool(cached),
            "allow_generate": bool(allow),
            "verdict": verdict or "error",
            "score": int(saved.get("score") or 0),
            "reasons": saved.get("reasons") if isinstance(saved.get("reasons"), list) else [],
            "text_hash": str(saved.get("text_hash") or text_hash),
            "gate_path": f"captures/{run_id}/gates/{sid}.json",
            "created_at": str(saved.get("created_at") or ""),
        }

    cached_obj = read_json(gate_path, default=None)
    if isinstance(cached_obj, dict):
        cached_hash = str(cached_obj.get("text_hash") or "").strip()
        cached_verdict = str(cached_obj.get("verdict") or "").strip().lower()
        if cached_hash and cached_hash == text_hash and cached_verdict:
            return _summarize(cached_obj, cached=True)

    if not enabled:
        return {
            "enabled": False,
            "cached": False,
            "allow_generate": True,
            "verdict": "disabled",
            "score": 10,
            "reasons": ["disabled"],
            "text_hash": text_hash,
            "gate_path": f"captures/{run_id}/gates/{sid}.json",
            "created_at": "",
        }

    if len(excerpt.strip()) < 200:
        saved = {
            "schema_version": 1,
            "created_at": utc_now_iso_z(),
            "run_id": run_id,
            "domain": str(domain or "").strip(),
            "method": str(method or "").strip(),
            "source_id": sid,
            "source_url": url,
            "source_title": title,
            "excerpt_chars": int(excerpt_chars),
            "text_hash": text_hash,
            "verdict": "fail",
            "score": 0,
            "reasons": ["too_short"],
            "good_signals": [],
            "bad_signals": ["too_short"],
            "llm_provider": getattr(llm, "provider", "") if llm else "",
            "llm_model": getattr(llm, "model", "") if llm else "",
        }
        write_json_atomic(gate_path, saved)
        return _summarize(saved, cached=False)

    if llm is None:
        saved = {
            "schema_version": 1,
            "created_at": utc_now_iso_z(),
            "run_id": run_id,
            "domain": str(domain or "").strip(),
            "method": str(method or "").strip(),
            "source_id": sid,
            "source_url": url,
            "source_title": title,
            "excerpt_chars": int(excerpt_chars),
            "text_hash": text_hash,
            "verdict": "error",
            "score": 0,
            "reasons": ["missing_llm_client"],
            "good_signals": [],
            "bad_signals": ["missing_llm_client"],
            "llm_provider": "",
            "llm_model": "",
        }
        write_json_atomic(gate_path, saved)
        return _summarize(saved, cached=False)

    messages = make_skill_gate_prompt(
        domain=str(domain or "").strip(),
        method=str(method or "").strip(),
        source_url=url,
        source_title=title,
        excerpt_text=excerpt,
    )
    prompt_sha = _prompt_sha(messages)

    out: dict[str, Any] | None = None
    last_err: Exception | None = None
    for attempt in range(0, 2):
        try:
            out = llm.chat_json(messages=messages, temperature=0.0, timeout_ms=timeout_ms)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))

    verdict = "error"
    score = 0
    reasons: list[str] = []
    good_signals: list[str] = []
    bad_signals: list[str] = []
    error_msg = ""
    error_type = ""

    if isinstance(out, dict):
        verdict = str(out.get("verdict") or "").strip().lower()
        if verdict not in {"pass", "maybe", "fail"}:
            verdict = "error"
        try:
            score = int(out.get("score") or 0)
        except Exception:
            score = 0
        score = max(0, min(10, int(score)))
        if isinstance(out.get("reasons"), list):
            reasons = [str(x).strip() for x in out.get("reasons") if str(x).strip()][:5]
        if isinstance(out.get("good_signals"), list):
            good_signals = [str(x).strip() for x in out.get("good_signals") if str(x).strip()][:8]
        if isinstance(out.get("bad_signals"), list):
            bad_signals = [str(x).strip() for x in out.get("bad_signals") if str(x).strip()][:8]
        if not reasons:
            reasons = ["no_reasons"]
    else:
        if last_err is not None:
            error_msg = str(last_err)
            error_type = type(last_err).__name__
        reasons = ["llm_call_failed"]

    saved = {
        "schema_version": 1,
        "created_at": utc_now_iso_z(),
        "run_id": run_id,
        "domain": str(domain or "").strip(),
        "method": str(method or "").strip(),
        "source_id": sid,
        "source_url": url,
        "source_title": title,
        "excerpt_chars": int(excerpt_chars),
        "text_hash": text_hash,
        "prompt_sha256": prompt_sha,
        "verdict": verdict,
        "score": int(score),
        "reasons": reasons,
        "good_signals": good_signals,
        "bad_signals": bad_signals,
        "llm_provider": getattr(llm, "provider", ""),
        "llm_model": getattr(llm, "model", ""),
        "error": error_msg,
        "error_type": error_type,
    }

    write_json_atomic(gate_path, saved)

    if _save_llm_artifacts_enabled():
        redact_urls = str(os.environ.get("LANGSKILLS_REDACT_URLS") or "").strip() == "1"
        write_json_atomic(
            gate_dir / f"{sid}.prompt.json",
            redact_obj(
                {
                    "created_at": utc_now_iso_z(),
                    "llm_provider": getattr(llm, "provider", ""),
                    "llm_model": getattr(llm, "model", ""),
                    "prompt_sha256": prompt_sha,
                    "messages": [m.to_dict() for m in messages],
                },
                redact_urls=redact_urls,
            ),
        )
        write_json_atomic(
            gate_dir / f"{sid}.response.json",
            redact_obj(
                {
                    "created_at": utc_now_iso_z(),
                    "llm_provider": getattr(llm, "provider", ""),
                    "llm_model": getattr(llm, "model", ""),
                    "output": out if isinstance(out, dict) else {"error": error_msg, "error_type": error_type},
                },
                redact_urls=redact_urls,
            ),
        )

    return _summarize(saved, cached=False)

