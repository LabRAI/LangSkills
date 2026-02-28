from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _tokenize(text: str) -> list[str]:
    s = str(text or "").lower()
    toks = [t for t in re.split(r"[^a-z0-9_./-]+", s) if t]
    # Prefer longer tokens (more discriminative)
    toks = [t for t in toks if len(t) >= 3]
    return toks[:40]


def _score_record(rec: dict[str, Any], tokens: list[str]) -> int:
    path = str(rec.get("path") or "").lower()
    qn = str(rec.get("qualified_name") or "").lower()
    kind = str(rec.get("kind") or "").lower()
    summary = " ".join([str(x or "") for x in (rec.get("summary_5_10_lines") or [])]).lower()
    hay = " ".join([qn, path, kind, summary])

    score = 0
    for t in tokens:
        if t in qn:
            score += 8
        elif t in path:
            score += 5
        elif t in summary:
            score += 3
        elif t in hay:
            score += 1

    # Small bonuses
    if kind == "module":
        score += 1
    if kind in {"function", "method"}:
        score += 2
    return score


@dataclass(frozen=True)
class QueryHit:
    path: str
    language: str
    source_type: str
    repo_url: str
    git_commit: str
    blob_sha: str
    line: int
    kind: str
    qualified_name: str
    signature: str
    score: int
    summary_lines: list[str]


def query_symbols(symbols: list[dict[str, Any]], question: str, *, top_k: int = 8) -> list[QueryHit]:
    tokens = _tokenize(question)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for rec in symbols:
        sc = _score_record(rec, tokens)
        if sc <= 0:
            continue
        ranked.append((sc, rec))
    ranked.sort(key=lambda x: -x[0])

    hits: list[QueryHit] = []
    for sc, rec in ranked[: max(1, int(top_k or 1))]:
        hits.append(
            QueryHit(
                path=str(rec.get("path") or ""),
                language=str(rec.get("language") or ""),
                source_type=str(rec.get("source_type") or ""),
                repo_url=str(rec.get("repo_url") or ""),
                git_commit=str(rec.get("git_commit") or ""),
                blob_sha=str(rec.get("blob_sha") or ""),
                line=int(rec.get("start_line") or 1),
                kind=str(rec.get("kind") or ""),
                qualified_name=str(rec.get("qualified_name") or ""),
                signature=str(rec.get("signature") or ""),
                score=int(sc),
                summary_lines=[str(x or "") for x in (rec.get("summary_5_10_lines") or []) if str(x or "").strip()][:10],
            )
        )
    return hits


def _short_symbol(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(rec.get("path") or ""),
        "language": str(rec.get("language") or ""),
        "source_type": str(rec.get("source_type") or ""),
        "repo_url": str(rec.get("repo_url") or ""),
        "git_commit": str(rec.get("git_commit") or ""),
        "blob_sha": str(rec.get("blob_sha") or ""),
        "line": int(rec.get("start_line") or 1),
        "kind": str(rec.get("kind") or ""),
        "qualified_name": str(rec.get("qualified_name") or ""),
        "signature": str(rec.get("signature") or ""),
        "tags": rec.get("tags") if isinstance(rec.get("tags"), list) else [],
    }


def build_evidence_pack(
    *,
    symbols: list[dict[str, Any]],
    hit: QueryHit,
    max_module: int = 8,
    max_callers: int = 8,
    max_callees: int = 8,
) -> dict[str, Any]:
    """
    Graph-ish expansion without requiring a resolved call graph:
    - same-module neighbors
    - best-effort callers/callees based on name matching
    """
    qn = str(hit.qualified_name or "")
    base = qn.split(".")[-1] if qn else ""
    path = str(hit.path or "")

    rec = None
    for r in symbols:
        if str(r.get("qualified_name") or "") == qn and str(r.get("path") or "") == path:
            rec = r
            break

    # Same-module symbols
    module_symbols: list[dict[str, Any]] = []
    if path:
        for r in symbols:
            if str(r.get("path") or "") != path:
                continue
            if str(r.get("qualified_name") or "") == qn:
                continue
            module_symbols.append(_short_symbol(r))
            if len(module_symbols) >= max(1, int(max_module or 1)):
                break

    callers: list[dict[str, Any]] = []
    if base:
        for r in symbols:
            if str(r.get("kind") or "") not in {"function", "method"}:
                continue
            calls = r.get("calls") if isinstance(r.get("calls"), list) else []
            if not calls:
                continue
            if any(base == str(c).split(".")[-1] for c in calls):
                callers.append(_short_symbol(r))
                if len(callers) >= max(1, int(max_callers or 1)):
                    break

    callees: list[dict[str, Any]] = []
    if rec and isinstance(rec.get("calls"), list):
        want = [str(c or "").split(".")[-1] for c in (rec.get("calls") or []) if str(c or "").strip()]
        want = [w for w in want if len(w) >= 2]
        seen: set[str] = set()
        for w in want:
            if w in seen:
                continue
            seen.add(w)
            for r in symbols:
                if str(r.get("kind") or "") not in {"function", "method"}:
                    continue
                q = str(r.get("qualified_name") or "")
                if q.endswith(f".{w}"):
                    callees.append(_short_symbol(r))
                    break
            if len(callees) >= max(1, int(max_callees or 1)):
                break

    return {
        "network_hints": (rec.get("network_hints") if isinstance(rec, dict) else []) or [],
        "writes": (rec.get("writes") if isinstance(rec, dict) else []) or [],
        "module_symbols": module_symbols,
        "callers": callers,
        "callees": callees,
    }
