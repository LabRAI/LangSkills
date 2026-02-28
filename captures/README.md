# `captures/`

Runtime output for **capture runs**.

Each run is written to `captures/<run-id>/` and is intended to be auditable and reproducible: it records the inputs, discovered sources, extracted evidence, generated skills, and validation reports.

## Typical structure

- `captures/<run-id>/manifest.json`: run metadata and source list.
- `captures/<run-id>/sources/<source_id>.json`: per-source evidence artifacts (extracted text, fingerprint, license info, etc.).
- `captures/<run-id>/skills/<domain>/<topic>/<slug>/...`: generated skill packages for the run.
- `captures/<run-id>/quality_report.md`: validation output and improvement suggestions.

## Notes

- This directory can become very large and is usually treated as disposable runtime output.
- `scripts/clean_workspace.sh` can delete it (dry-run by default).

See “How capture works” in the root README: `../README.md`.

