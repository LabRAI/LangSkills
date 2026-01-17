# Backend Full Verification Report（放弃 Pages → 本地后端“联网检索”）

Date: 2026-01-17

Environment:
- CWD: `/Users/shatianming/Downloads/LangSkills`
- Node: `v23.11.0`

Backend definition used in this report:
- “后端”= 静态分发/托管 `website/dist/` 的本地 HTTP 服务，用于替代 GitHub Pages。
- 入口：`scripts/serve-local.js`（`build-site` + `serve-site`），静态服务器为 `scripts/serve-site.js`。
- 客户端消费方式：
  - Website：同源拉取 `./index.json` 并在前端过滤；按需拉取 `./skills/**` markdown（`website/src/app.js`）。
  - CLI：`--base-url` 拉取 `index.json` 并过滤；按需拉取 markdown；参数化技能通过 `template` 拉取模板并渲染（`cli/skill.js`）。
  - Plugin：通过 `baseUrl` 拉取 `index.json` 并过滤；按需拉取 markdown；参数化技能渲染模板（`plugin/chrome/popup.js`）。

---

## 1) Executed backend tests (full commands + outputs)

### 1.1 `serve-local` automated smoke (PASS)

Command:
```bash
node scripts/test-serve-local.js
```

Output:
```txt
OK: serve-local(build+serve) passed
- outDir: /var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-serve-local-vZYZoe
- baseUrl: http://127.0.0.1:54472/
- skills_count: 102051
OK: serve-local(--no-build) passed
- baseUrl: http://127.0.0.1:51348/
- skills_count: 102051
```

Coverage (what the script asserts):
- `serve-local` can build+serve, and can serve with `--no-build`.
- HTTP endpoints work with expected content-types and `Cache-Control: no-store`:
  - `/` (HTML, title present)
  - `/index.json` (schema_version, skills_count, counts, length consistency)
  - `/app.js`, `/style.css`
  - Atomic markdown fetch: `skills/linux/filesystem/find-files/{library.md,skill.md,reference/sources.md}`
  - Template markdown fetch + placeholder presence: `skills/linux/m2-templates/parameterized-template/library.md` contains `{{id}}`
- Basic safety behavior:
  - `/skills/` directory returns 404
  - traversal attempt does not return 200
- CLI online mode against backend:
  - `cli/skill.js show linux/m2-param/p-000001 --file library --base-url <server>` renders `{{id}}`
  - `cli/skill.js show linux/m2-param/p-000001 --file skill --base-url <server>` renders `{{id}}`

### 1.2 Full local regression (PASS)

Command:
```bash
node scripts/self-check.js --m0 --m1 --m2 --skip-remote
```

Output:
```txt
OK   m0(repo-skeleton) - 30 paths OK
OK   agent(generator) - skills_count=42
OK   validate-skills - OK: 2052 skills validated.
OK   build-site - Built site: /Users/shatianming/Downloads/LangSkills/website/dist
Skills indexed: 102051
OK   m0(skills) - total=102051 (bronze=96776, silver=4720, gold=555)
OK   m2(site-index) - schema_version=2 probe=linux/filesystem/find-files
OK   m2(real-scale) - total=102051 parameterized=100000 (min=100000)
OK   serve-site(local) - http://127.0.0.1:4472/index.json (skills_count=102051)
OK   cli(online) - search/show OK
OK   cli(online,m2) - parameterized template render OK
OK   cli - search/show OK
OK   cli(m2) - parameterized template render OK
OK   render-topics-table - wrote /var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-topics-xoyWKU/topics_table.md
OK   runner - state=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-runs-FoR8xX/self-check-runner/state.json
OK   crawler - state=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-crawl-runs-UmS67c/self-check-crawl/crawl_state.json
OK   plugin(manifest) - host_permissions OK
OK   git-automation - dry-run + branch push OK
OK   create-pr(mock) - http://127.0.0.1:55990
OK   pages(remote) - skipped (--m1 offline default)
OK   m1(eval) - out=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/eval-report-MHbYw4/report.json (skills=2052)
OK   m1(lifecycle) - stale_gold=0
OK   m1(pr-score) - score=100
OK   m1(scale) - skills_count=2000
OK   m2(scale-index) - skills_count=100000 bytes=12571223
```

Notes:
- 这条命令是仓库当前“最大覆盖面”的本地回归入口，包含后端（serve-site）、CLI offline/online、M2 参数化渲染、mock PR、等。
- `--skip-remote` 明确跳过 Pages/真实 GitHub 线上闭环（该缺口见下方差距清单）。

### 1.3 “全仓库可发布级别”合规门禁 (FAIL, full output)

Command:
```bash
node scripts/validate-skills.js --strict --fail-on-license-review-all
```

Output:
```txt
Skill validation failed (81 issues):
- [integrations/slack/incoming-webhooks] sources.md License needs review for [1]: 'unknown'
- [integrations/slack/incoming-webhooks] sources.md License needs review for [2]: 'unknown'
- [integrations/slack/incoming-webhooks] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [3]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [1]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [2]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [3]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [1]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [2]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [3]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [1]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [2]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [3]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [1]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [2]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [3]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [1]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [2]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [3]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [1]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [2]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [3]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [4]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [1]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [2]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [3]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [1]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [2]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [1]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [2]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [1]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [2]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [4]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [1]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [2]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [3]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [1]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [2]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [3]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [1]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [2]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [3]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [1]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [2]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [3]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [1]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [2]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [3]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [1]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [2]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [3]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [1]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [2]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [3]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [1]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [2]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [3]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [1]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [2]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [3]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [4]: 'unknown'
```

---

## 2) Verdict: can the backend “fully execute” and “meet every requirement”?

### 2.1 Backend execution (serve-local as Pages replacement)

Status: ✅ 可完整执行（在“静态分发 + 客户端本地过滤检索”的口径下）
- 证据：`node scripts/test-serve-local.js` PASS（见 1.1）
- 证据：`node scripts/self-check.js --m0 --m1 --m2 --skip-remote` PASS（见 1.2）

### 2.2 Repo-wide “every requirement”

Status: ❌ 仍不能满足“每一个需求”（缺口见 Appendix B/Appendix C）
- “全仓库可发布级别”合规门禁仍失败（81 个 `License: unknown`）→ Missing-010
- 缺网站/插件浏览器级 e2e → Missing-011
- 多 domain 内容覆盖仍薄（多个 domain 仍为占位）→ Missing-012
- 若需要对外证据链：真实 GitHub PR/Release 线上闭环仍缺 → Missing-013
- 后端本身仍是“静态托管”，无服务端 query/search API、无 TLS/鉴权（若要公网服务会成为额外需求/缺口）

---

## Appendix A) Project parsing (verbatim): `docs/repo_inventory.md`

(Verbatim copy below)

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
- `scripts/serve-local.js`: build + serve local “Pages replacement” backend (HTTP).
- `scripts/test-serve-local.js`: automated serve-local backend smoke (HTTP + CLI).
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
- `scripts/serve-site.js`: static file server for `website/dist/`.
- `scripts/serve-local.js`: wrapper (build-site → serve-site) for local backend hosting.
- `cli/skill.js`: offline/online search/show/copy; supports parameterized skills from `skills/skillsets.json`.
- `website/src/app.js`: web UI (loads `index.json`, fetches per-skill markdown; renders templates).
- `plugin/chrome/popup.js`: Chrome extension popup (loads `index.json`, fetches library.md; renders templates).
- `eval/harness/`: task runner + metrics aggregation.

## Config & Data
- `agents/configs/<domain>.yaml`: domain seeds + allow/deny + topics.
- `agents/configs/sources.yaml`: tiered sources registry.
- `docs/domains/*.md`: domain scope notes.
- `skills/<domain>/<topic>/<slug>/`: skill content + `reference/` evidence.
- `skills/skillsets.json`: parameterized skill generators (10万级 index 扩量口径).
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

# local backend (Pages replacement): build + serve in one command
node scripts/serve-local.js --out website/dist --host 127.0.0.1 --port 4173

# serve-local backend smoke
node scripts/test-serve-local.js

# one-off generation
node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-out --overwrite --capture

# long-run scheduler
node agents/orchestrator/run.js --domain linux --run-id linux-orch --loop --crawl-max-pages 200 --extract-max-docs 200

# eval harness (example)
node eval/harness/run.js --skills-root skills --tasks eval/tasks/linux/smoke.json --out runs/eval-report.json --out-md runs/eval-report.md

# CLI (offline / local repo)
node cli/skill.js search find
node cli/skill.js show linux/m2-param/p-000001 --file library

# CLI (online / HTTP, via serve-local or serve-site)
node cli/skill.js search find --base-url http://127.0.0.1:4173/
node cli/skill.js show linux/m2-param/p-000001 --file library --base-url http://127.0.0.1:4173/
```

## Risks / Unknowns
- `github_repo` sources are listed but not yet wired into orchestrator discovery.
- Only `linux`/`productivity` domains are configured by default.
- License policy allow/deny rules are incomplete (see `docs/mohu.md`).
- CI uses Node 20; local runtime is not pinned (no `package.json`).
- No dedicated test framework beyond `scripts/self-check.js` and `scripts/validate-skills.js`.
- Link checking in CI uses `lychee` GitHub Action; local `lychee` is not wired as a script.
- Local “network” access for Chrome plugin is currently limited by `plugin/chrome/manifest.json` host permissions (includes `127.0.0.1`/`localhost`, not arbitrary LAN IPs).

---

## Appendix B) Ideal vs reality gaps (verbatim): `docs/gap_ideal_vs_reality.md`

(Verbatim copy below)

# Ideal vs Reality Gap Report（放弃 Pages → 本地后端“联网检索”）

Date: 2026-01-17

> 目标：在“用本地后端服务替代 GitHub Pages”前提下，完整验证可执行性，并把仓库里**已写明的理想目标/门禁/里程碑**与**当前现实实现/证据**逐条对照，列出全部差距（含合规灰名单、线上验证缺口、e2e 缺口、内容覆盖缺口）。

## 0. 口径与范围

### 0.1 本报告采用的“理想需求来源”
- `docs/plan.md`（Q2–Q6 的核心目标与优先级）
- `README.md`（设计不变量 + M0/M1/M2 里程碑 DoD）
- `docs/milestone_gap.md`（已跑通 vs 现实发布门禁差距）
- `docs/mohu.md` + `docs/verify_log.md`（实现项与验证日志）
- `docs/governance.md`、`docs/license_policy.md`、`SAFETY.md`（治理/合规/安全边界）

### 0.2 “放弃 Pages”的解释
- 不再要求 `https://<owner>.github.io/<repo>/` 可访问。
- 分发/检索的“线上端”由本地 HTTP 后端替代：`scripts/serve-local.js`（本质为 `build-site` + `serve-site`）。
- 仍可以保留 GitHub Actions/Release/PR 自动化作为“可选”，但不再作为本地检索必需条件。

## 1. 本地后端（serve-local）是否可完整执行

### 1.1 理想目标（替代 Pages 的最低功能集）
- 能一键产出并托管 `website/dist/`（含 `index.json` 与 `skills/**` 文件树）。
- 网站（`website/src/app.js`）、CLI（`cli/skill.js --base-url`）、插件（`plugin/chrome/popup.js`）都能通过 HTTP 使用同一份 `index.json` 检索并按需拉取 markdown。
- 对 M2 参数化技能：能通过 `template` 拉取模板 markdown，并在分发端完成 `{{id}}/{{slug}}/...` 渲染。

### 1.2 现实实现（代码/入口）
- 后端入口（build+serve）：`scripts/serve-local.js`
- 静态 HTTP 服务器：`scripts/serve-site.js`
- 自动化测试：`scripts/test-serve-local.js`

### 1.3 已运行的测试与结果（证据）
- ✅ `node scripts/test-serve-local.js`：PASS  
  - 覆盖：build+serve、`--no-build`、`/index.json`、`/`、`app.js/style.css`、`library.md`、404、路径逃逸尝试不返回 200、CLI online 模板渲染（`linux/m2-param/p-000001`）。
- ✅ `node scripts/self-check.js --m2`：PASS  
  - 覆盖：build-site、serve-site(local)、cli(online)、cli(online,m2) 模板渲染等（详见 `docs/verify_log.md`）。

### 1.4 现实差距（本地后端相对“理想后端”的不足）
- **无服务端搜索 API**：当前是“下载 `index.json` 后在前端/CLI 侧过滤”，不是“后端 query → 返回结果”。100k 时 `index.json` 体积与拉取频率会影响体验。
- **无鉴权/无 TLS/无多用户隔离**：适合本机或可信局域网，不适合作为公网服务。
- **插件跨设备访问受限**：`plugin/chrome/manifest.json` host_permissions 只包含 `127.0.0.1/localhost`，如果后端绑定到 LAN IP（例如 `0.0.0.0` 并用 `192.168.x.x` 访问），插件默认不一定能直接访问。

## 2. docs/plan.md（Q2–Q6）理想 vs 现实

> 结论：核心工程链路大多已落地并可本地回归；但“全仓库可发布级别合规（license 灰名单清零）”仍是最大硬缺口之一。

1) Local-model support (Q2)  
- 理想：生成流程支持 `mock|ollama` 等 provider 且可离线回归。  
- 现实：✅ 已实现（见 `docs/mohu.md` Missing-001 + `docs/verify_log.md` Missing-001）。

2) Quality + License guard (Q3)  
- 理想：严格门禁 + 可审计来源/抓取证据 + 原文拷贝审计 + license 风险策略。  
- 现实：⚠️ 部分满足  
  - ✅ `--strict` 可跑通并做结构/引用/来源字段/域名策略校验（PASS，但有 warnings）。  
  - ✅ 原文拷贝审计能力存在（需显式启用 `--require-no-verbatim-copy` 并提供 cache）。  
  - ❌ “全仓库清零灰名单”仍失败：`--fail-on-license-review-all`（见第 5 节）。

3) Long-running bots (Q4)  
- 理想：长跑队列、断点续跑、去重、速率控制。  
- 现实：✅ 已实现（`agents/runner/*`、`agents/orchestrator/*`；见 `docs/mohu.md` Missing-003、Missing-005 与 verify_log）。

4) Auto git push (Q5)  
- 理想：默认 dry-run、安全推送/回滚，并能在自检覆盖关键路径。  
- 现实：✅ 关键路径已覆盖（`scripts/git-automation.js` + self-check 的临时 repo 推送回归）。  
  - ⚠️ 若仍希望“真实 GitHub PR 创建/Release 发布”作为对外证据链：需要线上跑一次（本地只做 mock/create-pr）。

5) Crawl scope + scaling (Q6)  
- 理想：per-domain seeds/allowlist/denylist + 可扩展“发现→入队→生成→校验→去重→发布”。  
- 现实：⚠️ 工程框架具备，但内容与 domain 覆盖不足（见第 7 节“内容覆盖缺口”）。

## 3. README 里程碑（M0/M1/M2）理想 vs 现实

### 3.1 M0（硬 DoD 9 条）
1. Repo 骨架：✅ 自检覆盖（`self-check m0(repo-skeleton)` PASS）。  
2. Skill 标准 v1：✅ `validate-skills --strict` 强制结构/引用绑定/来源字段。  
3. Bot MVP（真实自动生成 PR）：⚠️ 代码具备，但缺“线上真实 GitHub PR”验证闭环（本地主要覆盖 mock）。  
4. Validator MVP：✅ 已可作为合并门禁（CI 跑 `--strict`）。  
5. Skills ≥ 50（20 silver、5 gold）：✅ 当前满足；且 M2 下总体规模更高。  
6. 官网 MVP：✅ 本地可跑（`build-site` + `serve-local/serve-site`）；⚠️ 缺浏览器级 e2e（见第 6 节）。  
7. CLI MVP：✅（离线 + 在线模式均可；含参数化实例 `linux/m2-param/p-000001`）。  
8. 插件 MVP：⚠️ manifest/host_permissions 回归有；缺浏览器级 e2e/交互回归。  
9. 发布 v0.1-alpha：⚠️ 若放弃 Pages，则“站点对外可访问”不再是必需；但 Release/Tag 资产是否作为对外发布仍需明确与线上验证。

### 3.2 M1
- Skills ≥ 2,000：✅（当前 index skills_count 已达标；但多 domain 仍薄）。  
- 周更 release + 变更日志 + eval 报告：⚠️ 本地 eval 报告可落盘；线上 Release 资产是否跑通需一次真实验证（若仍需要对外）。  
- PR 自动评分：✅（`pr-score` 自检覆盖）。  
- 生命周期机制运行：⚠️ 有检测与门禁，但“降级/归档”策略是否自动执行与对外解释仍需明确。

### 3.3 M2
- 参数化/组合化/去重扩量：⚠️ 参数化已落地并达成 100k；组合化（composite）目前仍是预留口径（`counts.composite=0`）。  
- bot 矩阵化（多 domain/config 驱动）：❌ 现状域覆盖明显不足（见第 7 节）。  
- Eval 与质量治理成为事实标准：⚠️ eval harness/治理门禁存在，但“证据链对外可复用/可对比”的整理仍不完整（尤其当放弃 Pages 后，需要新的对外发布策略）。

## 4. 现实实现快照（规模/分布/门禁）

### 4.1 站点索引规模（`website/dist/index.json`）
- `skills_count=102051`
- `counts.atomic=2051`
- `counts.parameterized=100000`
- `counts.composite=0`

### 4.2 Domain 覆盖（按 index.json）
- `linux`: total=102042（atomic=2042、parameterized=100000）
- `productivity`: atomic=8
- `integrations`: atomic=1

## 5. 合规差距（License 灰名单未清零：81 个 unknown）

### 5.1 现状
- ✅ `node scripts/validate-skills.js --strict`：PASS（但有 81 条 License review warnings）
- ❌ `node scripts/validate-skills.js --strict --fail-on-license-review-all`：FAIL（81 issues）

### 5.2 全量失败清单（不省略）
```
Skill validation failed (81 issues):
- [integrations/slack/incoming-webhooks] sources.md License needs review for [1]: 'unknown'
- [integrations/slack/incoming-webhooks] sources.md License needs review for [2]: 'unknown'
- [integrations/slack/incoming-webhooks] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/acl-basics] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/compress-gzip-xz] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/copy-move-cp-mv] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/disk-usage-du-df] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/mount-umount] sources.md License needs review for [3]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [1]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [2]: 'unknown'
- [linux/filesystem/safe-delete] sources.md License needs review for [3]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [1]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [2]: 'unknown'
- [linux/network/connectivity-ping-traceroute] sources.md License needs review for [3]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [1]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [2]: 'unknown'
- [linux/network/ports-ss-lsof] sources.md License needs review for [3]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [1]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [2]: 'unknown'
- [linux/packages/package-manager-basics] sources.md License needs review for [3]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [1]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [2]: 'unknown'
- [linux/process/background-nohup] sources.md License needs review for [3]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [1]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [2]: 'unknown'
- [linux/process/pkill-killall] sources.md License needs review for [3]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [1]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [2]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [3]: 'unknown'
- [linux/process/ps-top-kill] sources.md License needs review for [4]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [1]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [2]: 'unknown'
- [linux/scheduling/cron-basics] sources.md License needs review for [3]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [1]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [2]: 'unknown'
- [linux/security/sudoers-best-practice] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [1]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [2]: 'unknown'
- [linux/ssh/scp-rsync] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [1]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [2]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [3]: 'unknown'
- [linux/ssh/ssh-keys] sources.md License needs review for [4]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [1]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [2]: 'unknown'
- [linux/system/date-time-tz] sources.md License needs review for [3]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [1]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [2]: 'unknown'
- [linux/system/env-path] sources.md License needs review for [3]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [1]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [2]: 'unknown'
- [linux/system/permissions-umask] sources.md License needs review for [3]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [1]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [2]: 'unknown'
- [linux/system/resources-free-vmstat] sources.md License needs review for [3]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [1]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [2]: 'unknown'
- [linux/systemd/journalctl-logs] sources.md License needs review for [3]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [1]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [2]: 'unknown'
- [linux/systemd/systemctl-service-status] sources.md License needs review for [3]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [1]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [2]: 'unknown'
- [linux/text/view-files-less-tail] sources.md License needs review for [3]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [1]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [2]: 'unknown'
- [linux/text/xargs-basics] sources.md License needs review for [3]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [1]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [2]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [3]: 'unknown'
- [linux/users/user-group-management] sources.md License needs review for [4]: 'unknown'
```

## 6. 测试差距（浏览器级 e2e 缺失）
- 网站 UI 的 e2e：❌（当前主要是构建/索引/HTTP smoke；未做 Playwright 等浏览器交互回归）。
- Chrome 插件交互 e2e：❌（当前仅 manifest/host_permissions 回归）。

## 7. 内容覆盖差距（多 domain 仍薄）

### 7.1 当前 `skills/` 元数据覆盖（metadata.yaml）
```
cloud       meta=0 hidden=0 kinds=-
data        meta=0 hidden=0 kinds=-
devtools    meta=0 hidden=0 kinds=-
integrations meta=1 hidden=0 kinds=atomic:1
linux       meta=2043 hidden=1 kinds=atomic:2042,template:1
productivity meta=8 hidden=0 kinds=atomic:8
travel      meta=0 hidden=0 kinds=-
web         meta=0 hidden=0 kinds=-
```

### 7.2 现实差距
- `skills/web|cloud|data|travel|devtools`：基本为占位（0 条 metadata.yaml 技能）。
- `integrations`：只有 1 个示例 topic（Slack incoming webhooks）。
- M2 的 100k 规模目前几乎全部落在 `linux` 的 parameterized 实例上，尚未形成“多 domain、多来源、多策略”的矩阵化扩量。

## 8. 若未来仍要“对外发布级别”能力（当前仍缺的线上闭环）
- 真实 GitHub PR 创建/分支推送/权限策略：本地只做 mock/临时 repo 回归，线上仍需跑一次确认（若要对外背书）。
- Release/tag 资产可访问性：若要把 eval 报告/产物对外长期留存，仍需线上跑一次验证（即便不使用 Pages）。

---

## Appendix C) Open items (verbatim excerpt): `docs/mohu.md` Missing-010..013

(Verbatim copy below)

- [ ] Missing-010: 清零 License 灰名单（unknown）以达成“全仓库可发布级别”合规门禁
  - Location: `skills/**/reference/sources.md`, `scripts/validate-skills.js`, `scripts/license-policy.json`
  - Acceptance:
    - `node scripts/validate-skills.js --strict --fail-on-license-review-all` 通过（0 个 `License needs review`）
  - Evidence:
    - 当前 `node scripts/validate-skills.js --strict --fail-on-license-review-all` 失败（81 issues；均为 `License: unknown`）。
  - Notes:
    - 这是一项“内容合规”工作：需要逐条确认每个来源的真实 license（或换来源/删来源）。

- [ ] Missing-011: 网站/插件的浏览器级 E2E 回归（覆盖检索/打开/复制/模板渲染）
  - Location: `website/`, `plugin/chrome/`, `scripts/`
  - Acceptance:
    - 提供可执行 e2e 命令（例如 Playwright）：能在 CI 或本地无头跑通
    - 覆盖最小关键路径：
      - website：加载 `index.json`、搜索、打开技能、拉取 `library.md`/`skill.md`/`sources.md`，并验证 parameterized 模板渲染
      - plugin：加载 `index.json`、搜索、打开详情、复制 `library.md`（或至少验证 fetch+render 路径）
  - Evidence:
    - 当前自检以 build/manifest/HTTP smoke 为主；缺少浏览器交互自动化（见 `docs/milestone_gap.md`）。
  - Notes:
    - 若暂不做插件 e2e，可先做 website e2e 并把插件留作后续 Missing（需明确口径）。

- [ ] Missing-012: 多 domain 内容扩充（web/cloud/data/travel/devtools + integrations 多 topic）
  - Location: `skills/web/`, `skills/cloud/`, `skills/data/`, `skills/travel/`, `skills/devtools/`, `skills/integrations/`, `agents/configs/`
  - Acceptance:
    - 每个 domain 至少有一批可被索引的真实 skills（`metadata.yaml` 存在且不为模板 hidden）
    - `node scripts/validate-skills.js --strict` 通过
    - `node scripts/build-site.js --out website/dist` 后 `index.json` 中各 domain skills 数量不为 0（按约定阈值验收）
  - Evidence:
    - 当前 `skills/web|cloud|data|travel|devtools` 为占位（0 条 `metadata.yaml`）；`integrations` 仅 1 个示例 topic。

- [ ] Missing-013:（可选）线上真实 PR/Release 闭环（即便放弃 Pages 也需要对外证据链时）
  - Location: `.github/workflows/`, `scripts/create-pr.js`, `scripts/git-automation.js`, `docs/milestone_gap.md`
  - Acceptance:
    - GitHub 上真实运行一次：
      - 自动创建 PR（非 mock）
      - 自动发布 Release/tag 资产可访问（例如 eval report）
  - Evidence:
    - 当前本地主要覆盖 mock/create-pr 与临时 repo push；不等价于真实 GitHub 权限/网络/分支策略的线上验证。
  - Notes:
    - 若仓库只用于本地私有分发，可将此项降级为“不做”；但对外开源/可公开访问时应补齐。

