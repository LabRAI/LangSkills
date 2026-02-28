# `config/`

This directory contains LangSkills configuration files (primarily `config/skill_config.json`) that control discovery, canonicalization, validation gates, and defaults.

## Contents

| Path | Purpose |
|---|---|
| `skill_config.json` | Master runtime configuration (domains, canonicalization, quality gates, license policy, env surface). |
| `autopilot.example.json` | Autopilot supervisor config template (used by `langskills autopilot-init`). |
| `autopilot_schedule.safe.example.json` | Safe scheduler template (low-risk tools only). |
| `autopilot_schedule.full.example.json` | Full scheduler template (includes medium-risk tools; requires explicit allowlist). |
| `report_schedule.example.json` | Example report scheduler config for `langskills report-scheduler`. |
| `解析.md` | Notes about the config surface (debugging pointers). |

## Key files (details)

- `skill_config.json`: master runtime configuration used by `langskills/config.py`.
  - Defines `domain_config` (seed URLs + GitHub/forum queries)
  - Defines `canonicalization` rules (URL normalization before hashing)
  - Defines validation/quality gates and license policy defaults
  - Lists supported environment variables in the `env` section (used as a reference + optional overrides)

## Common changes

- Add or tune domain seeds under `domain_config.<domain>.web_urls`.
- Adjust GitHub discovery under `domain_config.<domain>.github` (query, min stars, pushed-after).
- Tune forum discovery under `domain_config.<domain>.forum`.
- Add URL normalization rules under `canonicalization` to improve dedupe stability.

## Autopilot templates

- `autopilot.example.json`: Autopilot supervisor config template (used by `langskills autopilot-init`).
- `autopilot_schedule.safe.example.json`: Safe scheduler template (low-risk tools only).
- `autopilot_schedule.full.example.json`: Full scheduler template (includes medium-risk tools like planner/evolve; requires explicit allowlist in the schedule).

See the root README for end-to-end usage: `../README.md`.
