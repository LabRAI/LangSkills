from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..repo_understanding.contracts import write_contracts
from ..repo_understanding.graphs import build_call_graph, build_import_graph
from ..repo_understanding.ingest import (
    DEFAULT_BIG_FILE_BYTES,
    classify_tags,
    detect_language,
    is_binary_file,
    iter_repo_files,
    mtime_iso,
)
from ..repo_understanding.state import INDEXER_VERSION, build_repo_state, changed_paths, load_repo_state
from ..repo_understanding.symbol_index import load_symbol_index_jsonl, write_symbol_index_jsonl
from ..utils.fs import write_json_atomic
from ..utils.git import get_git_commit
from ..utils.time import utc_now_iso_z


def cli_repo_index(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai repo-index")
    parser.add_argument("--out-dir", default="captures", help="Output directory (default: captures)")
    parser.add_argument("--repo", default="", help="Remote GitHub repo (URL or owner/repo). When set, index that repo snapshot instead of local.")
    parser.add_argument("--ref", default="", help="Remote ref (branch/tag/sha). Default: repo default branch.")
    parser.add_argument("--max-files", type=int, default=0, help="Remote-only: max files to download/analyze (0 = no limit)")
    parser.add_argument("--incremental", action="store_true", help="Reuse previous index for unchanged files (requires repo_state.json)")
    parser.add_argument("--state", default="", help="Path to repo_state.json (default: <out-dir>/repo_state.json)")
    parser.add_argument("--big-file-bytes", type=int, default=DEFAULT_BIG_FILE_BYTES, help="Files larger than this are structure-only")
    parser.add_argument("--contracts-out", default="", help="Where to write contracts.md (default: docs/contracts.md for local, <out-dir>/contracts.md for remote)")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Glob to include (repeatable). Default includes core src + config/docs/tests/CI + top-level docs",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob to exclude (repeatable). Default excludes common generated dirs",
    )
    ns = parser.parse_args(argv)

    out_dir = Path(ns.out_dir)
    repo_root = Path(__file__).resolve().parents[2]
    # Best-effort: load `.env` so GitHub/OpenAI/Tavily tokens can be provided via repo-local config.
    try:
        from ..env import load_dotenv

        load_dotenv(repo_root)
    except Exception:
        pass
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Remote GitHub mode: index a repo snapshot into <out-dir> without touching local docs/.
    if str(ns.repo or "").strip():
        from ..repo_understanding.github_remote import index_github_repo

        include_globs = list(ns.include or []) or ["*"]
        exclude_globs = list(ns.exclude or []) or ["**/__pycache__/**", ".venv/**", "node_modules/**", "dist/**", "build/**", "target/**"]

        big_file_bytes = int(ns.big_file_bytes or DEFAULT_BIG_FILE_BYTES)
        os.environ["LANGSKILLS_REPO_INDEX_BIG_FILE_BYTES"] = str(big_file_bytes)

        res = index_github_repo(
            repo=str(ns.repo),
            ref=str(ns.ref or ""),
            out_dir=out_dir,
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            big_file_bytes=big_file_bytes,
            max_files=int(ns.max_files or 0),
        )

        tree_path = out_dir / "repo_tree.json"
        tree_obj = {
            "schema_version": 1,
            "generated_at": res.get("generated_at"),
            "repo_url": res.get("repo_url"),
            "full_name": res.get("full_name"),
            "ref": res.get("ref"),
            "git_commit": res.get("git_commit"),
            "files": (res.get("repo_tree") or {}).get("files") if isinstance(res.get("repo_tree"), dict) else [],
            "counts": {"files_total": int(res.get("files_total") or 0)},
        }
        write_json_atomic(tree_path, tree_obj)

        sym_path = out_dir / "symbol_index.jsonl"
        with sym_path.open("w", encoding="utf-8") as f:
            for r in res.get("symbol_records") or []:
                if isinstance(r, dict):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

        symbols = load_symbol_index_jsonl(sym_path)
        import_graph = build_import_graph(symbols)
        call_graph = build_call_graph(symbols)
        write_json_atomic(out_dir / "import_graph.json", import_graph)
        write_json_atomic(out_dir / "call_graph.json", call_graph)

        contracts_path = Path(str(ns.contracts_out or "").strip()) if str(ns.contracts_out or "").strip() else (out_dir / "contracts.md")
        if not contracts_path.is_absolute():
            contracts_path = (repo_root / contracts_path).resolve()
        # Use the snapshot dir for context if present; otherwise fall back to out_dir.
        snapshot_dir = Path(str(res.get("snapshot_dir") or out_dir))
        write_contracts(repo_root=snapshot_dir, symbols=symbols, out_path=contracts_path)

        # Remote repo_state.json: content hashes are blob shas (for audit / future incremental).
        state_path = Path(ns.state) if str(ns.state or "").strip() else (out_dir / "repo_state.json")
        if not state_path.is_absolute():
            state_path = (repo_root / state_path).resolve()
        files_state: dict[str, dict[str, Any]] = {}
        for fe in tree_obj.get("files") or []:
            if not isinstance(fe, dict):
                continue
            p = str(fe.get("path") or "").strip()
            if not p:
                continue
            files_state[p] = {
                "size_bytes": int(fe.get("size_bytes") or 0),
                "mtime": "",
                "sha256": str(fe.get("blob_sha") or ""),
                "hash_kind": "github_blob_sha",
            }
        write_json_atomic(
            state_path,
            {
                "schema_version": 1,
                "indexer_version": int(INDEXER_VERSION),
                "repo_url": res.get("repo_url"),
                "git_commit": res.get("git_commit"),
                "ref": res.get("ref"),
                "generated_at": res.get("generated_at"),
                "files": files_state,
            },
        )

        summary = {
            "generated_at": res.get("generated_at"),
            "repo_url": res.get("repo_url"),
            "full_name": res.get("full_name"),
            "ref": res.get("ref"),
            "git_commit": res.get("git_commit"),
            "out_dir": out_dir.as_posix(),
            "tree_path": tree_path.as_posix(),
            "symbol_index_path": sym_path.as_posix(),
            "contracts_path": contracts_path.as_posix(),
            "import_graph_path": (out_dir / "import_graph.json").as_posix(),
            "call_graph_path": (out_dir / "call_graph.json").as_posix(),
            "repo_state_path": state_path.as_posix(),
            "incremental": False,
            "changed_paths": [],
            "big_file_bytes": big_file_bytes,
            "symbol_index": {"files_analyzed": int(res.get("files_downloaded") or 0), "records_written": len(symbols)},
            "counts": {
                "files_total": int(res.get("files_total") or 0),
                "files_downloaded": int(res.get("files_downloaded") or 0),
                "symbols_total": len(symbols),
                "import_edges": len(import_graph.get("edges") or []),
                "call_edges": len(call_graph.get("edges") or []),
            },
        }
        write_json_atomic(out_dir / "repo_index_summary.json", summary)
        try:
            from ..repo_understanding.metrics import update_metrics

            update_metrics(out_dir / "metrics.json", section="repo_index", data=summary)
        except Exception:
            pass
        print(json.dumps(summary["counts"], ensure_ascii=False))
        return 0

    include_globs = list(ns.include or []) or [
        "langskills",
        "scripts",
        "config",
        "docs",
        "tests",
        ".github",
        "langskills_cli.py",
        "README*",
        "plan*.md",
        "pyproject.toml",
        "setup.cfg",
        "requirements*.txt",
    ]
    # Exclude generated roots (top-level), but keep langskills/skills (core code).
    exclude_globs = list(ns.exclude or []) or [
        ".venv/**",
        "**/__pycache__/**",
        "node_modules/**",
        "skills/**",
        "captures/**",
        "dist/**",
        "runs/**",
    ]

    files = iter_repo_files(repo_root, include_globs=include_globs, exclude_globs=exclude_globs)

    git_commit = get_git_commit(repo_root)

    state_path = Path(ns.state) if str(ns.state or "").strip() else (out_dir / "repo_state.json")
    if not state_path.is_absolute():
        state_path = (repo_root / state_path).resolve()
    prev_state = load_repo_state(state_path) if ns.incremental else None
    if ns.incremental and isinstance(prev_state, dict) and int(prev_state.get("indexer_version") or 0) != int(INDEXER_VERSION):
        prev_state = None  # force full rebuild when indexer changes
    new_state = build_repo_state(repo_root=repo_root, files=files, prev_state=prev_state, git_commit=git_commit, generated_at=utc_now_iso_z())
    write_json_atomic(state_path, new_state)
    changed = changed_paths(prev_state, new_state) if ns.incremental else set()

    # Provide incremental hint to symbol index writer (best-effort, env-based contract).
    if ns.incremental:
        os.environ["LANGSKILLS_REPO_INDEX_CHANGED"] = "\n".join(sorted(changed))

    tree_path = out_dir / "repo_tree.json"
    big_file_bytes = int(ns.big_file_bytes or DEFAULT_BIG_FILE_BYTES)
    os.environ["LANGSKILLS_REPO_INDEX_BIG_FILE_BYTES"] = str(big_file_bytes)
    file_entries: list[dict[str, object]] = []
    state_files = new_state.get("files") if isinstance(new_state.get("files"), dict) else {}
    for rf in files:
        rel = rf.rel_path
        abs_path = rf.abs_path
        meta = state_files.get(rel) if isinstance(state_files, dict) else {}
        size_bytes = int(meta.get("size_bytes") or rf.size_bytes)
        mtime = str(meta.get("mtime") or mtime_iso(abs_path))
        sha = str(meta.get("sha256") or "")
        binary = is_binary_file(abs_path)
        big = int(size_bytes) > big_file_bytes
        ignored = bool(binary)
        ignore_reason = "binary" if binary else ""
        analysis = "structure_only" if binary or big else "full"
        analysis_reason = "binary" if binary else ("big_file" if big else "")
        file_entries.append(
            {
                "path": rel,
                "language": detect_language(rel),
                "size_bytes": int(size_bytes),
                "mtime": mtime,
                "sha256": sha,
                "ignored": ignored,
                "ignore_reason": ignore_reason,
                "analysis": analysis,
                "analysis_reason": analysis_reason,
                "tags": classify_tags(rel),
            }
        )

    tree_obj = {
        "schema_version": 1,
        "generated_at": utc_now_iso_z(),
        "repo_root": repo_root.as_posix(),
        "git_commit": git_commit,
        "files": file_entries,
        "counts": {"files_total": len(files)},
    }
    write_json_atomic(tree_path, tree_obj)

    sym_path = out_dir / "symbol_index.jsonl"
    sym_summary = write_symbol_index_jsonl(repo_root=repo_root, files=files, out_path=sym_path)
    symbols = load_symbol_index_jsonl(sym_path)

    import_graph = build_import_graph(symbols)
    call_graph = build_call_graph(symbols)
    write_json_atomic(out_dir / "import_graph.json", import_graph)
    write_json_atomic(out_dir / "call_graph.json", call_graph)

    contracts_path = Path(str(ns.contracts_out or "").strip()) if str(ns.contracts_out or "").strip() else (repo_root / "docs" / "contracts.md")
    if not contracts_path.is_absolute():
        contracts_path = (repo_root / contracts_path).resolve()
    write_contracts(repo_root=repo_root, symbols=symbols, out_path=contracts_path)

    summary = {
        "generated_at": utc_now_iso_z(),
        "repo_root": repo_root.as_posix(),
        "git_commit": git_commit,
        "out_dir": out_dir.as_posix(),
        "tree_path": tree_path.as_posix(),
        "symbol_index_path": sym_path.as_posix(),
        "contracts_path": contracts_path.as_posix(),
        "import_graph_path": (out_dir / "import_graph.json").as_posix(),
        "call_graph_path": (out_dir / "call_graph.json").as_posix(),
        "repo_state_path": state_path.as_posix(),
        "incremental": bool(ns.incremental),
        "changed_paths": sorted(changed) if ns.incremental else [],
        "big_file_bytes": big_file_bytes,
        "symbol_index": sym_summary,
        "counts": {
            "files_total": len(files),
            "symbols_total": len(symbols),
            "import_edges": len(import_graph.get("edges") or []),
            "call_edges": len(call_graph.get("edges") or []),
        },
    }
    write_json_atomic(out_dir / "repo_index_summary.json", summary)
    try:
        from ..repo_understanding.metrics import update_metrics

        update_metrics(out_dir / "metrics.json", section="repo_index", data=summary)
    except Exception:
        pass

    print(json.dumps(summary["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_repo_index())
