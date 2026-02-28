# `langskills/postprocess/`

Postprocessing for run outputs: dedupe clustering and “combo skill” generation.

## What it does

- Clusters similar skills within a run.
- Optionally generates merged “combo skills” and matrices from near-duplicates.

## Key files

- `run.py`: main postprocess entrypoint used by `langskills_cli.py postprocess ...`.
- `dedupe.py`: similarity scoring and clustering logic.

## Tuning (env vars)

- `LANGSKILLS_DEDUPE_THRESHOLD` (0..1, default 0.25)
- `LANGSKILLS_MAX_COMBOS` (default 3, max 5)

See `../../README.md` for the end-to-end workflow.
