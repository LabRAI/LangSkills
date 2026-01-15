## Tree

```
/
  README.md
  plan.md                      # historical long-form plan draft
  LICENSE, LICENSE-docs
  CHANGELOG.md, CONTRIBUTING.md, SAFETY.md, SECURITY.md
  .github/workflows/           # CI + build-site + link-check + agent runs
  agents/                      # generator + configs + capture + runner + crawler + PR templates
  agents/configs/sources.yaml  # global sources registry (Tier1 docs + Tier0 upstream repos)
  agents/extractor/            # DocItem -> TopicCandidates (writes runs/<run-id>/candidates.jsonl)
  agents/orchestrator/         # scheduler: crawler + extractor (+ runner) + metrics
  agents/adapters/             # source adapters (sitemap/openapi/github/manpage; some are scaffolding)
  cli/                         # node cli/skill.js (search/show/copy/open)
  docs/                        # governance/taxonomy/format/domain boundaries + logs
  patterns/                    # reusable prompting/rag/tool-use/eval/safety notes
  plugin/chrome/               # Chrome extension (search/copy/open)
  scripts/                     # validate/build/serve/self-check/git automation helpers
  skills/                      # skills dataset (domain/topic/slug folders)
  website/src/                 # static site sources (reads index.json)
  website/dist/                # built static site (generated index.json + assets)
  .cache/web/                  # fetch cache for capture/crawler (ignored by git)
  runs/                        # runner/crawler state (ignored by git)
```

## Entry Points

- `agents/run_local.js` — Generate skills from `agents/configs/<domain>.yaml`; supports `--capture` (fetch sources + write evidence) and `--llm-provider` rewrites (mock/ollama/openai).
- `agents/generator/linux_capture.js` — Linux capture specs + fetch+cache+evidence rendering (URLs + sha256/bytes/cache hit/miss + License field).
- `agents/llm/index.js` — LLM provider abstraction (`mock`/`ollama`/`openai`) + `rewriteMarkdown()` used to polish captured markdown.
- `agents/runner/run.js` — Long-running topic runner (queue + resume + loop); persists `runs/<run-id>/state.json`.
- `agents/crawler/run.js` — Seeds → discovery → dedupe → enqueue; enforces `source_policy` and persists `runs/<run-id>/crawl_state.json` + `crawl_log.jsonl`.
- `agents/extractor/run.js` — Reads `crawl_state.json` + `.cache/web/` and emits `runs/<run-id>/candidates.jsonl` (+ `extractor_state.json` for resume).
- `scripts/validate-skills.js` — Skill gate (structure/Steps<=12/Sources>=3); `--strict` adds citations + fetch evidence + safety notes + license fields + source_policy; optional verbatim-copy audit via `--require-no-verbatim-copy`.
- `scripts/self-check.js` — End-to-end smoke (generator/capture/validate/build/serve/cli/plugin/crawler/runner/git-automation/optional remote Pages).
- `scripts/git-automation.js` — Safe git automation (dry-run by default; optional branch create/commit/push with retries).
- `agents/orchestrator/run.js` — Long-running scheduler: runs `crawler + extractor (+ runner)` in cycles and writes `runs/<run-id>/metrics.json` + `metrics_log.jsonl`.
- `scripts/build-site.js` — Build static site output: writes `index.json` and copies `website/src/*` into `website/dist/` (or `--out`).
- `scripts/serve-site.js` — Tiny HTTP server for `website/dist/` (default `127.0.0.1:4173`).
- `cli/skill.js` — CLI to list/search/show/copy/open skills by id.
- `plugin/chrome/popup.js` — Chrome popup UI; fetches `<baseUrl>/index.json` and copies `library.md` content.
- `website/src/app.js` — Static web UI; fetches `./index.json` and renders search + detail panel.

## Core Modules

- `skills/**` → The primary “dataset”: each skill is a folder with `skill.md`, `library.md`, `metadata.yaml`, and `reference/*.md`.
- `agents/configs/**` → Domain configs: `topics` + `source_policy.allow_domains/deny_domains` + `seeds` for crawler discovery.
- `agents/configs/sources.yaml` → Global sources registry (Tier1 docs + Tier0 upstream skills repos; config-first scaling).
- `docs/domains/**` → Domain scope + preferred source types + out-of-scope constraints (policy docs).
- `scripts/**` → Build/validate/dev utilities used locally and by GitHub Actions.
- `website/**`, `cli/**`, `plugin/**` → Distribution surfaces (web/cli/chrome).

## Config & Data

- Skills layout: `skills/<domain>/<topic>/<slug>/...` (see `docs/taxonomy.md` and `docs/skill-format.md`).
- Domain configs: `agents/configs/<domain>.yaml` (topics + risk/level + `source_policy` + `seeds`).
- Sources registry: `agents/configs/sources.yaml` (shared sources; referenced by domain configs via `sources.primary[]`).
- Fetch cache: `.cache/web/*.txt` (raw fetched pages keyed by URL hash; ignored by git via `.gitignore`).
- Runner state: `runs/<run-id>/state.json` (ignored by git via `.gitignore`).
- Crawler state: `runs/<run-id>/crawl_state.json` and `runs/<run-id>/crawl_log.jsonl` (ignored by git via `.gitignore`).
- Extractor state: `runs/<run-id>/extractor_state.json` + `candidates.jsonl` (ignored by git via `.gitignore`).
- Orchestrator metrics: `runs/<run-id>/metrics.json` + `metrics_log.jsonl` (ignored by git via `.gitignore`).
- Built site artifacts: `website/dist/index.json` + `index.html/style.css/app.js`.
- Remote index (optional): `scripts/self-check.js` reads `SKILL_REMOTE_INDEX_URL` (default GitHub Pages index) unless `--skip-remote`.

## How To Run

```bash
# 0) Repo smoke (recommended)
node scripts/self-check.js --skip-remote

# 1) Generate skeleton skills from config
node agents/run_local.js --domain linux --out skills

# 2) Generate skills with capture (fetch + evidence) (requires network)
node agents/run_local.js --domain linux --out skills --overwrite --capture --capture-strict

# 3) Strict validation (citations + fetch evidence + safety + license + policy)
node scripts/validate-skills.js --strict

# 4) Verbatim-copy audit (requires fetch cache)
node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web

# 5) Long-running runner (days/weeks; persists runs/<run-id>/state.json)
node agents/runner/run.js --domain linux --out skills --overwrite --capture --loop --sleep-ms 30000 --cycle-sleep-ms 600000

# 6) Crawl discovery (days/weeks; persists runs/<run-id>/crawl_state.json + crawl_log.jsonl)
node agents/crawler/run.js --domain linux --max-pages 0 --loop --sleep-ms 3000 --cycle-sleep-ms 600000

# 7) Extract candidates from crawled docs (resume-safe)
node agents/extractor/run.js --domain linux --run-id linux-crawl-weekly --max-docs 200

# 8) Orchestrate crawl + extract (+ optional generate) with metrics
node agents/orchestrator/run.js --domain linux --run-id linux-orch-weekly --loop --crawl-max-pages 200 --extract-max-docs 200 --cycle-sleep-ms 600000

# 9) Build + serve the static site
node scripts/build-site.js --out website/dist
node scripts/serve-site.js --dir website/dist --port 4173

# 10) CLI usage
node cli/skill.js search find
node cli/skill.js show linux/filesystem/find-files --file library

# 11) Git automation (dry-run by default)
node scripts/git-automation.js --paths skills --branch bot/test --dry-run
```

## Risks / Unknowns

- Amb-001: “网页端的 integration” 的范围定义（生成集成类 skills vs 浏览器自动化 vs 作为分发入口）未定。
- Amb-002: License policy（允许/禁止/需人工复核的 license 列表）仍需业务决策；当前仅强制记录 `License:` 字段与来源域名策略。
- Amb-003: Git 认证与分支/PR 策略未定（push main vs bot branch+PR；GITHUB_TOKEN vs PAT/SSH）；当前提供安全 push 脚本但 PR 创建仍偏手动。
- Amb-004: “至少吃掉现有所有这些 library” 的具体库/站点清单未定；crawler 目前是 HTML href 发现（不做 JS 渲染/登录站点）。
- Amb-005: candidates → topics 的自动化入队/去重/参数化策略仍需进一步工程化（当前先把候选与覆盖率落盘，便于后续接入）。
