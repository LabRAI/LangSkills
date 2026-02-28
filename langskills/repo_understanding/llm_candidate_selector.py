from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from ..llm.factory import create_llm_from_env
from ..llm.types import ChatMessage
from ..skills.prompts import (
    make_repo_candidate_selector_prompt,
    make_repo_file_selector_prompt,
    make_repo_file_skill_prompt,
    make_repo_symbol_summary_prompt,
)
from ..utils.fs import write_json_atomic
from ..utils.hashing import sha256_hex
from ..utils.lang import resolve_output_language
from ..utils.redact import redact_obj, redact_text
from ..utils.text import truncate_text
from ..utils.time import utc_stamp_compact
from .llm_trace import write_llm_trace
from .symbol_index import load_symbol_index_jsonl


_SENSITIVE_PATH_RE = re.compile(
    r"(^|/)(\.env(\..+)?|\.git/|id_rsa(\.pub)?|id_ed25519(\.pub)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|.*\.crt|.*\.cer)$",
    flags=re.IGNORECASE,
)


def _is_sensitive_path(path: str) -> bool:
    p = str(path or "").replace("\\", "/").strip()
    if not p:
        return True
    if p == ".env" or p.startswith(".env."):
        # Keep .env.example only; everything else is assumed sensitive.
        return not p.endswith(".env.example")
    return bool(_SENSITIVE_PATH_RE.search(p))


def _is_safe_rel_path(path: str) -> bool:
    p = str(path or "").replace("\\", "/").strip()
    if not p:
        return False
    if p.startswith("/") or p.startswith("~"):
        return False
    if "://" in p:
        return False
    if p.startswith("../") or "/../" in p or p == "..":
        return False
    return True


def _is_available_file(fs_root: Path, rel_path: str) -> bool:
    if not _is_safe_rel_path(rel_path) or _is_sensitive_path(rel_path):
        return False
    root = fs_root.resolve()
    p = (root / rel_path).resolve()
    try:
        if not p.is_file():
            return False
        if not p.is_relative_to(root):
            return False
    except Exception:
        return False
    return True


def _safe_read_text(fs_root: Path, rel_path: str, *, max_bytes: int) -> str:
    if not _is_available_file(fs_root, rel_path):
        return ""
    root = fs_root.resolve()
    p = (root / rel_path).resolve()
    try:
        if not p.is_file():
            return ""
        if not p.is_relative_to(root):
            return ""
        data = p.read_bytes()[: max(0, int(max_bytes or 0))]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _score_symbol_for_target(rec: dict[str, Any], target: str) -> int:
    tags = rec.get("tags") if isinstance(rec.get("tags"), list) else []
    writes = rec.get("writes") if isinstance(rec.get("writes"), list) else []
    network = bool(rec.get("network"))
    k = str(target or "").lower()
    score = 0
    if k in {"workflow", "cli"}:
        if "entrypoint" in tags:
            score += 20
        if writes:
            score += 25
        if network:
            score += 15
        if str(rec.get("path") or "").startswith("langskills/skills/"):
            score += 10
    elif k == "module":
        if network:
            score += 15
        if rec.get("reads_env"):
            score += 10
        if writes:
            score += 10
    elif k == "troubleshooting":
        if "manifest" in tags or "quality_report" in tags:
            score += 15
    score += len(writes)
    return score


def _symbol_pool(symbols: list[dict[str, Any]], target: str, max_symbols: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for r in symbols:
        # Filter: keep only interesting records (entrypoint / writes / network).
        tags = r.get("tags") if isinstance(r.get("tags"), list) else []
        has_signal = ("entrypoint" in tags) or ("io_write" in tags) or bool(r.get("network")) or (r.get("writes") or [])
        if not has_signal:
            continue
        score = _score_symbol_for_target(r, target)
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("qualified_name") or "")))
    pool = []
    for score, r in scored[: max_symbols]:
        summary_lines = r.get("summary_5_10_lines") or []
        excerpt = " ".join(summary_lines)[:400]
        pool.append(
            {
                "qualified_name": r.get("qualified_name"),
                "kind": r.get("kind"),
                "path": r.get("path"),
                "start_line": r.get("start_line"),
                "tags": r.get("tags") if isinstance(r.get("tags"), list) else [],
                "writes": (r.get("writes") or [])[:6],
                "network": bool(r.get("network")),
                "reads_env": (r.get("reads_env") or [])[:6],
                "summary": (summary_lines or [])[:3],
                "excerpt": excerpt,
            }
        )
    return pool


def _extract_snippet(repo_root: Path, path: str, start_line: int, window: int = 80) -> str:
    raw = _safe_read_text(repo_root, path, max_bytes=120_000)
    if not raw:
        return ""
    lines = raw.replace("\r\n", "\n").split("\n")
    ln0 = max(0, (start_line or 1) - window)
    ln1 = min(len(lines), (start_line or 1) + window)
    snippet = "\n".join(f"{i+1:>4}: {lines[i]}" for i in range(ln0, ln1))
    return snippet


def _enrich_summaries_with_llm(
    *,
    fs_root: Path,
    pool: list[dict[str, Any]],
    llm,
    language: str,
    max_items: int = 40,
    window: int = 80,
) -> None:
    for i, entry in enumerate(pool[: max_items]):
        path = str(entry.get("path") or "")
        start_line = int(entry.get("start_line") or 1)
        snippet = _extract_snippet(fs_root, path, start_line, window=window)
        if not snippet:
            continue
        msgs = make_repo_symbol_summary_prompt(
            language=resolve_output_language(default=language or "en"),
            path=path,
            qualified_name=str(entry.get("qualified_name") or path),
            snippet=snippet,
        )
        try:
            out = llm.chat_json(messages=msgs, temperature=0.0, timeout_ms=300_000)
            if isinstance(out, dict) and out.get("summary"):
                entry["summary"] = [str(out.get("summary"))]
                entry["excerpt"] = str(out.get("summary"))
        except Exception:
            continue


def _symbol_by_path_line(symbols: list[dict[str, Any]], path: str, line: int) -> dict[str, Any] | None:
    p = str(path or "").replace("\\", "/")
    for r in symbols:
        if str(r.get("path") or "").replace("\\", "/") != p:
            continue
        start = int(r.get("start_line") or 0)
        end = int(r.get("end_line") or 0)
        if end and start and start <= line <= end:
            return r
        if not end and start and abs(start - line) <= 12:
            return r
    return None


def select_candidates_with_llm(
    *,
    repo_root: str | Path,
    symbols: list[dict[str, Any]] | None,
    target: str,
    top_n: int,
    language: str = "en",
    docs_summary: str = "",
    max_symbols: int = 120,
    llm_model: str | None = None,
    dir_based: bool = False,
    index_dir: str | Path | None = None,
    index_path: str = "captures/symbol_index.jsonl",
    timeout_ms: int | None = None,
) -> list[dict[str, Any]]:
    """
    Use LLM to pick candidate skills from a repo index.
    Returns a list of candidate dicts; each will later be turned into a SkillSpec.
    """
    repo_root = Path(repo_root).resolve()
    language = resolve_output_language(default=language)
    symbols = symbols or load_symbol_index_jsonl(repo_root / "captures" / "symbol_index.jsonl")

    if not dir_based:
        raise RuntimeError("LLM candidates: symbol-based mode is disabled; use --llm-dir-candidates.")

    timeout = int(timeout_ms or str(os.environ.get("LANGSKILLS_LLM_TIMEOUT_MS") or "").strip() or 300_000)

    llm = create_llm_from_env(model_override=llm_model)

    index_dir_p = Path(index_dir).resolve() if index_dir else (repo_root / "captures")
    tree_path = index_dir_p / "repo_tree.json"
    snapshot_dir = index_dir_p / "repo_snapshot"
    fs_root = snapshot_dir if snapshot_dir.exists() else repo_root

    def _extract_list(out: Any) -> list[dict[str, Any]]:
        raw: list[dict[str, Any]] = []
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except Exception:
                out = {"response": out}
        if isinstance(out, list):
            raw = out
        elif isinstance(out, dict):
            if isinstance(out.get("candidates"), list):
                raw = out.get("candidates")  # type: ignore
            elif isinstance(out.get("files"), list):
                raw = out.get("files")  # type: ignore
            elif isinstance(out.get("response"), list):
                raw = out.get("response")  # type: ignore
            elif isinstance(out.get("response"), str):
                try:
                    cand = json.loads(out.get("response"))
                    if isinstance(cand, list):
                        raw = cand
                except Exception:
                    pass
        return raw

    def call_llm(msgs: list[ChatMessage], *, trace_kind: str, trace_extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            out = llm.chat_json(messages=msgs, temperature=0.0, timeout_ms=timeout)
            write_llm_trace(repo_root, kind=trace_kind, messages=msgs, response_obj=out, extra=trace_extra)
            return _extract_list(out)
        except Exception as e:
            write_llm_trace(
                repo_root,
                kind=trace_kind,
                messages=msgs,
                response_obj={"error": str(e), "error_type": type(e).__name__},
                extra=trace_extra,
            )
            raise

    # Directory-based: pick files then derive candidates.
    files_list = _list_files_for_llm(tree_path, fs_root=fs_root, max_files=300)
    if not files_list:
        raise RuntimeError(f"repo_tree has no readable files for LLM selection: {tree_path}")
    allowed_paths = {str(f.get("path") or "") for f in files_list if isinstance(f, dict) and str(f.get("path") or "")}
    file_msgs = make_repo_file_selector_prompt(
        language=language or "en",
        top_n=top_n,
        files=files_list,
        docs_summary=redact_text(docs_summary, redact_urls=False),
    )
    file_choices = call_llm(
        file_msgs,
        trace_kind="candidates.file_select",
        trace_extra={
            "target": target,
            "top_n": top_n,
            "tree_path": str(tree_path),
            "files_list_len": len(files_list),
            "llm_provider": getattr(llm, "provider", ""),
            "llm_model": getattr(llm, "model", ""),
            "timeout_ms": int(timeout),
        },
    )
    if not file_choices:
        raise RuntimeError("LLM file selector returned empty. See captures/llm_traces/*.json for prompt/response.")

    raw: list[dict[str, Any]] = []
    chosen_files: list[str] = []
    skipped_files: dict[str, str] = {}
    for fc in file_choices:
        path = str(fc.get("path") or "").strip()
        if not path:
            continue
        if path not in allowed_paths:
            skipped_files[path] = "not_in_repo_tree"
            continue
        chosen_files.append(path)
        content = _safe_read_text(fs_root, path, max_bytes=80_000)
        if not content:
            skipped_files[path] = "unreadable"
            continue

        skill_msgs = make_repo_file_skill_prompt(
            language=language or "en",
            path=path,
            content=redact_text(content, redact_urls=False),
            target=target,
            top_n=max(1, top_n),
            index_path=str(index_path or "captures/symbol_index.jsonl"),
        )
        out: list[dict[str, Any]] = []
        base_msgs = list(skill_msgs)
        for attempt in range(1, 4):
            out = call_llm(
                skill_msgs,
                trace_kind="candidates.file_to_skills",
                trace_extra={
                    "path": path,
                    "target": target,
                    "attempt": attempt,
                    "llm_provider": getattr(llm, "provider", ""),
                    "llm_model": getattr(llm, "model", ""),
                    "timeout_ms": int(timeout),
                },
            )
            bad: list[str] = []
            for c in out:
                if not isinstance(c, dict):
                    continue
                cid = str(c.get("id") or c.get("name") or "").strip() or "(unknown)"
                entrypoints_in = c.get("entrypoints") if isinstance(c.get("entrypoints"), list) else []
                entrypoints = [str(x or "").strip() for x in entrypoints_in if str(x or "").strip()]
                steps_in = c.get("steps") if isinstance(c.get("steps"), list) else []
                steps = [str(x or "").strip() for x in steps_in if str(x or "").strip()]
                if not entrypoints:
                    bad.append(f"{cid}: missing entrypoints")
                if not steps:
                    bad.append(f"{cid}: missing steps")
                if any("<URL>" in s for s in (entrypoints + steps)):
                    bad.append(f"{cid}: contains <URL>")
                if any(("http://" in s) or ("https://" in s) or ("file://" in s) for s in (entrypoints + steps)):
                    bad.append(f"{cid}: contains URL scheme (http/https/file)")
            if not out:
                bad.append("returned empty candidates array")
            if not bad:
                break
            # Retry with explicit feedback; still LLM-only.
            feedback = {
                "attempt": attempt,
                "errors": bad[:30],
                "rules": [
                    "Return JSON only; do not add explanations.",
                    "Do not include http://, https://, file://, or <URL> anywhere in entrypoints or steps.",
                    "If you need to refer to an endpoint, use a schemeless form like localhost:PORT/path (or a plain-text placeholder without a scheme).",
                    "Prefer using the repo-query template for entrypoints.",
                ],
                "previous_output_preview": truncate_text(json.dumps(out, ensure_ascii=False), 1800),
            }
            skill_msgs = base_msgs + [
                ChatMessage(
                    role="user",
                    content="Previous output did not follow the rules. Please fix it and output the full JSON again:\n"
                    + json.dumps(feedback, ensure_ascii=False, indent=2),
                )
            ]
        if not out:
            raise RuntimeError(f"LLM returned empty candidates for file: {path}. See captures/llm_traces/*.json.")
        raw.extend(out)

    if not chosen_files:
        raise RuntimeError("LLM returned no usable files after filtering. See captures/llm_traces/*.json.")
    if not raw:
        raise RuntimeError(f"LLM produced zero candidates from chosen_files={chosen_files}; skipped_files={skipped_files}")

    cleaned: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    problems: list[str] = []
    for cand in raw:
        if not isinstance(cand, dict):
            continue
        cid = str(cand.get("id") or cand.get("name") or "").strip()
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)

        entrypoints_in = cand.get("entrypoints") if isinstance(cand.get("entrypoints"), list) else []
        entrypoints = [str(x or "").strip() for x in entrypoints_in if str(x or "").strip()]
        steps_in = cand.get("steps") if isinstance(cand.get("steps"), list) else []
        steps = [str(x or "").strip() for x in steps_in if str(x or "").strip()]
        if not entrypoints:
            problems.append(f"{cid}: missing entrypoints")
        if not steps:
            problems.append(f"{cid}: missing steps")
        if any("<URL>" in s for s in (entrypoints + steps)):
            problems.append(f"{cid}: entrypoints/steps contain forbidden placeholder <URL>")
        if any(("http://" in s) or ("https://" in s) or ("file://" in s) for s in (entrypoints + steps)):
            problems.append(f"{cid}: entrypoints/steps contain forbidden URL scheme (http/https/file)")

        ev_in = cand.get("evidence") if isinstance(cand.get("evidence"), list) else []
        ev_out: list[dict[str, Any]] = []
        for ev in ev_in:
            if not isinstance(ev, dict):
                continue
            path = str(ev.get("path") or "").strip()
            try:
                line = int(ev.get("line") or 0)
            except Exception:
                line = 0
            if not path or line <= 0:
                continue
            rec = _symbol_by_path_line(symbols, path, line)
            if not rec:
                continue
            ev_out.append(
                {
                    "path": rec.get("path"),
                    "line": int(line),
                    "qualified_name": rec.get("qualified_name") or cand.get("qualified_name"),
                    "repo_url": rec.get("repo_url"),
                    "git_commit": rec.get("git_commit"),
                    "ref": rec.get("ref"),
                    "blob_sha": rec.get("blob_sha"),
                    "start_line": rec.get("start_line"),
                }
            )
        if not ev_out:
            problems.append(f"{cid}: evidence could not be mapped to symbol_index (path:line invalid)")
            continue
        if not entrypoints or not steps:
            continue

        cleaned.append(
            {
                "id": cid,
                "name": str(cand.get("name") or cid),
                "goal": str(cand.get("goal") or "").strip() or "not provided",
                "target": str(cand.get("target") or target),
                "entrypoints": entrypoints,
                "steps": steps,
                "evidence": ev_out,
                "priority_score": int(cand.get("priority_score") or 50),
                "reason": truncate_text(str(cand.get("reason") or ""), 400),
            }
        )

    if problems:
        raise RuntimeError(
            "LLM candidates invalid:\n- "
            + "\n- ".join(problems[:30])
            + ("\n(…truncated)" if len(problems) > 30 else "")
            + "\nSee captures/llm_traces/*.json for prompt/response."
        )
    if not cleaned:
        raise RuntimeError("LLM returned candidates, but none were usable. See captures/llm_traces/*.json.")

    cleaned.sort(key=lambda c: (-int(c.get("priority_score") or 0), str(c.get("id") or "")))

    # Persist for audit.
    try:
        selected = cleaned[:top_n]
        record = {
            "schema_version": 1,
            "target": target,
            "top_n": top_n,
            "language": language,
            "tree_path": str(tree_path),
            "files_list_len": len(files_list),
            "chosen_files": chosen_files,
            "skipped_files": skipped_files,
            "raw_candidates_len": len(raw),
            "llm_provider": getattr(llm, "provider", ""),
            "llm_model": getattr(llm, "model", ""),
            "timeout_ms": int(timeout),
            "candidates": selected,
        }
        record = redact_obj(record, redact_urls=False)

        out_root = repo_root / "captures" / "llm_candidates"
        out_root.mkdir(parents=True, exist_ok=True)
        stamp = utc_stamp_compact()
        h = sha256_hex(json.dumps(record, ensure_ascii=False))[:8]
        out_path = out_root / f"{stamp}-{h}.json"
        write_json_atomic(out_path, record)
        write_json_atomic(repo_root / "captures" / "llm_candidates_latest.json", record)
        # Keep backward compatibility for existing tooling that expects this path.
        write_json_atomic(repo_root / "captures" / "llm_candidates.json", record)
    except Exception:
        pass

    return cleaned[:top_n]


def _list_files_for_llm(tree_path: Path, *, fs_root: Path, max_files: int = 200) -> list[dict[str, Any]]:
    """
    Parse captures/*/repo_tree.json which is a flat list under `files`.
    """
    if not tree_path.exists():
        return []
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = tree.get("files") if isinstance(tree, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if bool(it.get("ignored")):
            continue
        path = str(it.get("path") or "").strip()
        if not path:
            continue
        if not _is_safe_rel_path(path) or _is_sensitive_path(path):
            continue
        if not _is_available_file(fs_root, path):
            continue
        out.append(
            {
                "path": path,
                "language": it.get("language") or "",
                "size_bytes": int(it.get("size_bytes") or 0),
                "tags": it.get("tags") if isinstance(it.get("tags"), list) else [],
            }
        )
        if len(out) >= max_files:
            break
    return out


def _read_file(fs_root: Path, path: str, max_bytes: int = 50_000) -> str:
    return _safe_read_text(fs_root, path, max_bytes=max_bytes)
