# `langskills/skills/`

Skill generation, gating, improvement, packaging, and publishing.

## Responsibilities

- Generate skill Markdown (`skill.md`) from extracted source text.
- Produce package v2 supporting files (`library.md`, `reference/*`) for library browsing.
- Run SkillGate (optional LLM filter) to decide whether a source is suitable for skill generation.
- Improve skills based on validation reports.
- Publish run outputs into the long-lived library under `skills/by-skill/<skill_id>/`.

## Key files

- `generate.py`: generates one skill package from one source artifact.
- `gate.py`: SkillGate logic (LLM pre-filter).
- `improve.py`: LLM-driven improvement passes for existing generated skills.
- `package_v2.py`: generates the package v2 “library view” and references.
- `publish.py`: license gating + normalization + publish into `skills/` and update `skills/index.json`.
- `prompts.py`: LLM prompts for routing/generation/improvement.
- `markdown_ops.py`: markdown normalization helpers (Sources/Evidence sections, code block enforcement, etc.).
- `coerce.py`: coercion/parsing utilities for LLM outputs.

See “Stable IDs” and the pipeline overview in `../../README.md`.
