# `langskills/`

This is the core Python package for LangSkills: CLI wiring, configuration, the capture pipeline, source fetchers, skill generation, validation, and publishing.

## Entrypoints

- Repo root wrapper: `../langskills_cli.py` → calls `langskills.cli.main`.
- Module entrypoint: `python3 -m langskills ...` → runs `langskills/__main__.py`.

## What this package is responsible for

- Parsing CLI arguments and dispatching subcommands (`cli.py` + `scripts/`).
- Loading configuration from `config/skill_config.json` and environment (`config.py`, `env.py`).
- Discovering and fetching sources (`sources/`).
- Generating and improving skill packages (`skills/`, `postprocess/`).
- Validating and publishing into the long-lived library under `../skills/`.
- Running a persistent queue worker (`queue/`, `scripts/runner.py`).

## Subdirectories

- `llm/`: LLM provider abstraction (`openai` / `ollama`).
- `sources/`: source discovery + fetch/extract + evidence artifacts.
- `skills/`: skill generation, SkillGate, prompts, publishing.
- `queue/`: persistent queue store and scheduling.
- `postprocess/`: dedupe and “combo skill” generation.
- `repo_understanding/`: repo indexing and “skill from repo” tooling.
- `scripts/`: implementations for `langskills_cli.py <command>`.
- `utils/`: shared helpers (hashing, fs, retry, time, markdown ops, etc.).

See the root README for the end-to-end flow and examples: `../README.md`.

