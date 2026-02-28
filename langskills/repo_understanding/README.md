# `langskills/repo_understanding/`

Repository indexing and “skill from repo” tooling.

This module can index a codebase (local or GitHub) into structured artifacts (symbols, call graphs, runbooks) and can synthesize skills from repository context.

## What it produces (typical)

Artifacts are written under `captures/` (for example):

- `captures/repo_tree.json`, `captures/repo_state.json`
- `captures/symbol_index.jsonl`
- `captures/import_graph.json`, `captures/call_graph.json`
- `captures/llm_traces/*.json` (when LLM-assisted selection is used)

## Key files

- `symbol_index.py`: static symbol extraction and indexing.
- `graphs.py`: import/call graph utilities.
- `github_remote.py`: GitHub repo indexing (API/raw fetch).
- `runbook.py`, `render.py`: runbook generation.
- `llm_candidate_selector.py`, `llm_writer.py`: LLM-assisted selection and writing.
- `query.py`: query surfaces over the produced artifacts.

See CLI commands in `../../README.md` (repo-index/repo-runbook/repo-query/skill-from-repo).
