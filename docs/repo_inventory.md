# Repo Inventory

## Tree
- .github/ (workflows, issue/PR templates)
- agents/ (capture/generate/orchestrate pipelines + configs)
- cli/ (skill search/show CLI)
- docs/ (plan, governance, domains, repo inventory)
- eval/ (eval harness + tasks + reports)
- patterns/ (cross-skill patterns)
- plugin/ (Chrome extension)
- scripts/ (build, validate, automation, self-check)
- skills/ (skill dataset)
- website/ (static site sources)
- .cache/ (local fetch cache, not committed)
- runs/ (run state + metrics; ignored except placeholders)
- root docs: README.md, LICENSE, LICENSE-docs, SAFETY.md, SECURITY.md

## Entry Points
- `scripts/self-check.js`: local end-to-end regression (M0/M1/M2).
- `scripts/self-check.ps1`: PowerShell wrapper for `scripts/self-check.js`.
- `scripts/validate-skills.js`: strict skill gate (structure, citations, sources, license fields).
- `scripts/build-site.js`: build `website/dist/index.json` + static assets.
- `scripts/serve-site.js`: serve built site locally.
- `scripts/git-automation.js`: dry-run or branch push automation.
- `agents/run_local.js`: generate one skill (capture + optional LLM rewrite).
- `agents/runner/run.js`: long-running topic queue with resume.
- `agents/crawler/run.js`: crawl seeds and persist URL state.
- `agents/extractor/run.js`: extract candidates from cached snapshots.
- `agents/orchestrator/run.js`: looped scheduler for crawler/extractor/runner.
- `cli/skill.js`: search/show skills from `website/dist/index.json`.
- `plugin/chrome/manifest.json`: Chrome extension entry.
- `eval/harness/run.js`: run eval tasks and emit JSON/Markdown reports.

## Core Modules
- `agents/llm/`: LLM providers (`mock|ollama|openai`) and rewrite helper.
- `agents/generator/linux_capture.js`: capture pipeline + sources evidence.
- `agents/crawler/`: seed discovery, dedupe, allow/deny enforcement.
- `agents/extractor/`: candidate extraction + resume state.
- `agents/runner/`: topic queue + resume state (`runs/<run-id>/state.json`).
- `agents/orchestrator/`: cycle scheduler + metrics.
- `scripts/validate-skills.js`: repo-wide gate for skills format/evidence.
- `scripts/build-site.js`: site index builder for web/CLI/plugin.
- `eval/harness/`: task runner + metrics aggregation.

## Config & Data
- `agents/configs/<domain>.yaml`: domain seeds + allow/deny + topics.
- `agents/configs/sources.yaml`: tiered sources registry.
- `docs/domains/*.md`: domain scope notes.
- `skills/<domain>/<topic>/<slug>/`: skill content + `reference/` evidence.
- `.cache/web/`: raw fetch cache for capture/audit (ignored).
- `runs/<run-id>/`: crawl/extract/runner state + metrics (ignored).

## How To Run
```bash
# Milestone regressions (recommended)
node scripts/self-check.js --m0 --with-capture --skip-remote
node scripts/self-check.js --m1
node scripts/self-check.js --m2

# baseline health check
node scripts/self-check.js --skip-remote

# strict gate
node scripts/validate-skills.js --strict

# build + serve site
node scripts/build-site.js --out website/dist
node scripts/serve-site.js --dir website/dist --port 4173

# one-off generation
node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-out --overwrite --capture

# long-run scheduler
node agents/orchestrator/run.js --domain linux --run-id linux-orch --loop --crawl-max-pages 200 --extract-max-docs 200

# eval harness (example)
node eval/harness/run.js --skills-root skills --tasks eval/tasks/linux/smoke.json --out runs/eval-report.json --out-md runs/eval-report.md
```

## Risks / Unknowns
- `github_repo` sources are listed but not yet wired into orchestrator discovery.
- Only `linux`/`productivity` domains are configured by default.
- License policy allow/deny rules are incomplete (see `docs/mohu.md`).
- CI uses Node 20; local runtime is not pinned (no `package.json`).
- No dedicated test framework beyond `scripts/self-check.js` and `scripts/validate-skills.js`.
- Link checking in CI uses `lychee` GitHub Action; local `lychee` is not wired as a script.
