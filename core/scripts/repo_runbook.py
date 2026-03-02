from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..repo_understanding.runbook import run_golden_workflows


def cli_repo_runbook(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai repo-runbook")
    parser.add_argument("--out", default="captures/run_index.jsonl", help="Output JSONL (default: captures/run_index.jsonl)")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--provider", default="openai", help="LLM provider for full mode (openai|ollama)")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    records = run_golden_workflows(repo_root=repo_root, out_jsonl=ns.out, mode=str(ns.mode), provider=str(ns.provider))
    print(json.dumps({"runs": len(records), "out": str(ns.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_repo_runbook())
