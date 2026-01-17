# Repo Inventory

## Tree
- `.github/` (CI, lint, link-check, build-site, agent-generate, eval, lifecycle)
- `agents/` (crawler/extractor/runner/orchestrator + generators + LLM providers)
- `cli/` (offline/online search/show/copy)
- `docs/` (plan, mohu backlog, governance, gap reports, verification logs)
- `eval/` (eval harness + tasks + reports)
- `patterns/` (cross-skill patterns/snippets)
- `plugin/` (Chrome extension: search/copy UI)
- `scripts/` (validation, site build/serve, automation, self-check, e2e)
- `skills/` (skill dataset + templates + parameterized generators)
- `website/` (static site sources; runtime loads `index.json` + markdown on demand)
- `runs/` (local run state + logs + metrics; typically ignored)
- `.cache/` (local fetch cache; typically ignored)

## Entry Points
- `scripts/self-check.js`: widest local regression entry (`--m0/--m1/--m2`, defaults to skipping remote checks for M1+).
- `scripts/validate-skills.js`: strict gate (format/citations/source evidence/license/source_policy/verbatim audit).
- `scripts/build-site.js`: builds `website/dist/` (static assets + `index.json` + `skills/**` markdown tree).
- `scripts/serve-site.js`: static HTTP server for `website/dist/`.
- `scripts/serve-local.js`: “Pages replacement” wrapper (build-site → serve-site).
- `scripts/test-serve-local.js`: automated backend smoke (headers + 404/traversal + CLI online render).
- `scripts/e2e-ui.js` / `npm run e2e`: Playwright e2e for website + plugin UI flows.
- `agents/orchestrator/run.js`: long-running scheduler (Tier0 ingest → crawl → extract → optional generate) + metrics.
- `agents/crawler/run.js`: seed crawl + allow/deny domain enforcement + resume state/log.
- `agents/extractor/run.js`: cached snapshot → candidates (`runs/<run-id>/candidates.jsonl`) + resume state/log.
- `agents/runner/run.js`: long-running topic queue with resume (`runs/<run-id>/state.json`).
- `agents/run_local.js`: generate a single topic (capture + optional LLM rewrite).
- `scripts/git-automation.js`: branch/commit/push (dry-run by default; `--execute` to push).
- `scripts/create-pr.js`: create GitHub PR via API (requires `GITHUB_TOKEN`).
- `cli/skill.js`: search/show offline, or online via `--base-url/--index-url`.
- `website/src/app.js`: web search UI (loads `index.json`, fetches markdown, renders templates).
- `plugin/chrome/popup.js`: extension search/copy UI (loads `index.json` from configured `baseUrl`).

## Core Modules
- `agents/llm/`: provider abstraction (`mock|ollama|openai`) + markdown rewrite constraints.
- `agents/generator/*`: capture/render logic that emits `reference/sources.md` evidence blocks.
- `agents/crawler/`: URL discovery/fetch/dedupe + `runs/<run-id>/crawl_state.json` + `crawl_log.jsonl`.
- `agents/extractor/`: heading extraction + `runs/<run-id>/candidates.jsonl` + `extractor_state.json`.
- `agents/orchestrator/`: cycle scheduler + `runs/<run-id>/metrics.json` + `metrics_log.jsonl`.
- `agents/runner/`: topics queue executor + resume state (topic status per cycle).
- `scripts/validate-skills.js`: CI-aligned repo gate.
- `scripts/build-site.js`: index builder consumed by website/CLI/plugin (supports parameterized expansion via `skills/skillsets.json`).

## Config & Data
- Domain configs: `agents/configs/<domain>.yaml` (topics, seeds, `source_policy` allow/deny, `sources.primary[]` binding).
- Source registry: `agents/configs/sources.yaml` (tiered sources; includes Tier0 repos + Tier1 docs seeds).
- Skill data: `skills/<domain>/<topic>/<slug>/` (`skill.md`, `library.md`, `metadata.yaml`, `reference/*`).
- M2 parameterized generators: `skills/skillsets.json` (expands into index entries; templates can be `hidden: true`).
- Fetch cache: `.cache/web/` (raw snapshots used by capture/audit).
- Runs: `runs/<run-id>/` (crawler/extractor/orchestrator/runner state + logs + metrics).

## How To Run
```bash
# Install (needed for Playwright e2e)
npm install
# If browsers are missing:
npx playwright install chromium

# End-to-end regressions (offline; skips remote checks)
node scripts/self-check.js --m0 --m1 --m2 --skip-remote

# Strict gates
node scripts/validate-skills.js --strict
node scripts/validate-skills.js --strict --fail-on-license-review-all

# Build + serve locally (Pages replacement)
node scripts/serve-local.js --out website/dist --host 127.0.0.1 --port 4173
node scripts/test-serve-local.js

# Browser-level UI e2e (website + plugin)
npm run e2e

# Long-running bot (crawl + extract + optional generate; writes metrics/state to runs/<run-id>/)
node agents/orchestrator/run.js --domain linux --run-id linux-weekly --loop --sleep-ms 5000 --cycle-sleep-ms 600000
```

## Risks / Unknowns
- No “candidates → new topics → new skills” curator pipeline yet (`agents/curator/README.md`); discovered candidates are persisted but not auto-promoted into generation.
- Online GitHub PR/Release evidence chain is not verified in this workspace (`docs/mohu.md` Missing-013); local tests cover mock PR + local push only.
- “Local backend over LAN/public” security scope is not fixed (`docs/mohu.md` Amb-005): TLS/auth/rate-limit/plugin host_permissions need a decision.
- M2 “10万” definition is still ambiguous for “真实 skills vs parameterized index entries” (`docs/mohu.md` Amb-006).
