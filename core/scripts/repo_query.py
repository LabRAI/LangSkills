from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..repo_understanding.query import build_evidence_pack, query_symbols
from ..repo_understanding.symbol_index import load_symbol_index_jsonl


def cli_repo_query(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai repo-query")
    parser.add_argument("question", help="Question to answer (lexical evidence-backed search)")
    parser.add_argument("--index", default="captures/symbol_index.jsonl", help="Path to symbol_index.jsonl")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="Output machine JSON")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    idx = Path(ns.index)
    if not idx.is_absolute():
        idx = (repo_root / idx).resolve()

    symbols = load_symbol_index_jsonl(idx)
    hits = query_symbols(symbols, ns.question, top_k=int(ns.top or 8))

    if ns.json:
        print(
            json.dumps(
                [
                    {
                        "path": h.path,
                        "language": h.language,
                        "source_type": h.source_type,
                        "repo_url": h.repo_url,
                        "git_commit": h.git_commit,
                        "blob_sha": h.blob_sha,
                        "line": h.line,
                        "kind": h.kind,
                        "qualified_name": h.qualified_name,
                        "signature": h.signature,
                        "score": h.score,
                        "summary_lines": h.summary_lines,
                        "context": build_evidence_pack(symbols=symbols, hit=h),
                    }
                    for h in hits
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for h in hits:
        loc = f"{h.path}:{h.line}"
        lang = f"{h.language} " if h.language else ""
        print(f"- {loc} [{lang}{h.kind}] {h.qualified_name} (score={h.score})")
        if h.repo_url and h.git_commit:
            print(f"  repo: {h.repo_url} @ {h.git_commit}")
        if h.signature:
            print(f"  sig: {h.signature}")
        for ln in h.summary_lines:
            print(f"  - {ln}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_repo_query())
