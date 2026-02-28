# `langskills/scripts/`

Implementation modules for `langskills_cli.py <command>`.

The top-level CLI parser lives in `langskills/cli.py` and dispatches to functions implemented in this package.

## Examples

- `runner.py`: persistent queue worker and staged pipeline execution.
- `validate_skills.py`: library and run validation logic.
- `build_site.py`: generates `dist/` from `skills/index.json`.
- `reindex_skills.py`: rebuilds `skills/index.json` from `skills/by-skill/`.
- `dir_docs.py`: generates per-directory `DIR_DOCS.md` file inventories (optional tooling).
- `source_audit.py`: audits source providers and writes a report under `docs/`.

See the root README command table: `../../README.md`.
