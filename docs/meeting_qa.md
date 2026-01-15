# Meeting Q&A (Q1–Q6)

这份文档用于回答会议里的 6 个问题（结合本 repo 的真实实现与可复现命令）。如果需要逐条“证据”，优先引用 `docs/verify_log.md`。

## Q1. Repo 架构和开会看到的 repo 一样吗？区别是什么，为什么改？

本 repo 的核心形态是：**dataset（`skills/`）+ 生成/抓取/门禁（`agents/`,`scripts/`）+ 分发（`website/`,`cli/`,`plugin/`）+ CI（`.github/workflows/`）**。

对齐你提到的几类 repo（以各 repo 的 README/目录结构为准），本 repo 在“技能”层面和它们的共同点是：**每个 skill 一个目录**，主文档保持短小，把长材料下沉到引用/附件（progressive disclosure）。常见 repo 角色大致分三类：

- **内容库**：例如 `anthropics/skills`、`K-Dense-AI/claude-scientific-skills`、`muratcankoylan/Agent-Skills-for-Context-Engineering`（技能内容为主，通常每个 skill 有一个 `SKILL.md`）。
- **标准/SDK**：例如 `agentskills/agentskills`（提供标准/文档/参考实现，不是内容库本体）。
- **本 repo（内容库 + 工具链 + 分发）**：除技能数据集外，还内置 crawler/runner/orchestrator、严格 validator、以及 web/cli/plugin 分发面。

本 repo 相对更偏“可治理/可审计/可分发”的差异点主要是：

- 增加了 **严格门禁与可审计证据链**：`scripts/validate-skills.js --strict`（步骤引用、抓取指纹、license 字段、来源白名单、无 TODO、无大段原文拷贝审计）。
- 增加了 **可长跑的执行器**：runner（topics 队列断点续跑）+ crawler（seeds→发现→入队、落盘 state/log）。
- 增加了 **安全的 git 自动化**：默认 dry-run，且有自检覆盖，避免机器人误推送。

目的：把“能生成”升级为“能长期跑、可审计、可回归、可安全自动化发布”的形态。

## Q2. 架构是否同时支持网页端 integration 和本地开源模型？

- **本地开源模型**：已支持（例如 Ollama）。入口：`agents/run_local.js` 的 `--llm-provider ollama --llm-model <model>`。
- **网页端**：
  - 已有分发与检索：静态网站 `website/`、Chrome 插件 `plugin/chrome/`、CLI `cli/`。
  - “integration” 的范围仍需定口径（见 `docs/mohu.md` 的 Amb-001）：是“生成集成类 skills（API/平台）”、还是“浏览器自动化”、还是“分发入口/插件”。

## Q3. Markdown 质量是否确认合理/精炼？是否逐条检查 license？

当前“质量确认”依赖 **门禁与证据**（可复现），而不是口头保证：

- 严格门禁：`node scripts/validate-skills.js --strict`
  - `Steps <= 12`、必须 `Sources>=3`
  - 关键步骤必须有 `[[n]]` 引用
  - `reference/sources.md` 必须包含 `License:` 字段与抓取指纹（bytes/sha256/cache hit/miss）
  - 来源域名必须符合 `agents/configs/<domain>.yaml` 的 allow/deny
- “疑似大段原文拷贝”审计：`node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web`

关于 “逐条检查 license”：目前实现是 **强制记录 `License:` 字段 + 白名单域名策略 + 原文拷贝审计**；但“允许/禁止/需人工复核的 license 列表”仍是策略问题（Amb-002），需要产品/法务口径落地。

## Q4. 多机器人长跑的数据源与迭代策略是否足够？会不会跑俩小时就结束？

为了支持“连续跑数天到数星期”，本 repo 把 bot 按 **source registry → crawler → extractor → runner → validator → git automation** 拆开，并且做到关键状态都可落盘可恢复（否则必然“跑完一批就停/重启就丢”）。

关键能力：

- **runner（长跑执行/断点续跑）**：`agents/runner/run.js`，状态落盘 `runs/<run-id>/state.json`，支持 `--loop` 与节流参数。
- **crawler（稳定数据源 + 扩展发现）**：`agents/crawler/run.js`，从 per-domain `seeds`（或 registry seeds）出发发现链接、去重入队；同时对每个 URL 记录最小状态机 `DISCOVERED/FETCHED/BLOCKED/ERROR`（含抓取指纹 `sha256/bytes/cache_file`），写入 `runs/<run-id>/crawl_state.json` 与 `crawl_log.jsonl`。
- **extractor（候选生成 + 断点续跑）**：`agents/extractor/run.js`，从 `.cache/web/` 的 raw snapshot 抽取 headings 形成 `TopicCandidates`，写入 `runs/<run-id>/candidates.jsonl`，并用 `runs/<run-id>/extractor_state.json` 记录已处理 URL+sha 以便长期迭代。
- **orchestrator（永续调度 + 覆盖率/吞吐指标）**：`agents/orchestrator/run.js` 组合 `crawler + extractor (+ runner)`，支持 `--loop` 常驻；每个 cycle 写出 `runs/<run-id>/metrics.json`/`metrics_log.jsonl`，用于回答“还剩多少没吃/是否在持续产出”。
- **sources registry（稳定数据源注册表）**：`agents/configs/sources.yaml` 维护 Tier1 官方/权威来源（可长期跑）+ Tier0 上游技能库（reference-only，不直接搬运全文），domain 用 `agents/configs/<domain>.yaml` 的 `sources.primary[]` 引用。

是否“跑俩小时就结束”取决于你是否设置上限：runner/crawler 都支持 `--loop` 且可把 `--max-pages` 设为 `0`（不限制）。

长期运行的“终止条件”也不再是“进程退出”，而是：

- **BUSY**：队列/候选持续有任务（持续产出）
- **IDLE**：队列暂空，但 orchestrator 仍常驻等待下一次 refresh/discover（不会退出）

“至少吃掉现有所有这些 library”的前提是：先明确要吃掉哪些库/站点清单与合规边界（Amb-004），再把它们固化到 `agents/configs/sources.yaml`（含 `license_policy` 与 allowlist），由 crawler/extractor 形成可量化 coverage 的 backlog；对上游 skills repo 建议做 **evidence+映射（reference-only）**，避免侵权与重复膨胀。

## Q5. 自动 git push 是否调试确保没问题？

已提供可复现自检：

- `scripts/git-automation.js`：默认 dry-run；`--execute` 才会创建分支/commit/push（带重试，默认恢复回起始 ref）。
- `node scripts/self-check.js --skip-remote`：会在临时 git repo + 本地 bare remote 中验证 **dry-run + 分支 push**（见 `docs/verify_log.md` 的 Missing-004）。

## Q6. 部署后会爬取哪里？内容足够多吗？如何高效 scale？

爬取范围是 “**domain seeds + source_policy allow/deny + sources registry**”：

- seeds：`agents/configs/<domain>.yaml` 的 `seeds:`（例如 `agents/configs/linux.yaml`、`agents/configs/productivity.yaml`、`agents/configs/integrations.yaml`）或 `agents/configs/sources.yaml` 中 domain 绑定的 Tier1 seeds（由 `sources.primary[]` 引用）。
- 强制执行：crawler/capture 都会按 allow/deny 过滤来源域名（不在白名单的 URL 会被阻断或不入队），并把 block 写入 `runs/<run-id>/crawl_log.jsonl` 以便审计。

scale 方式：

- 增加 sources（`agents/configs/sources.yaml`）与 domain allowlist（合法扩张范围），让“新增内容源”尽量变成只改 YAML。
- 多机器人并行：按 domain / seeds / run-id 分片，避免同一个 `runs/<run-id>` 被多个进程同时写。
- 用 `runs/<run-id>/metrics.json`/`metrics_log.jsonl` 跟踪 coverage/吞吐/错误；用 `crawl_log.jsonl` + `candidates.jsonl` 做可审计证据链。
- 扩展 adapters：`agents/adapters/` 提供 sitemap/openapi/github/manpage 等接口（部分仍是 scaffolding），用于把“爬哪里”变成可插拔实现。

## 证据与产物在哪里？

- skills 数据：`skills/<domain>/<topic>/<slug>/...`
- 严格门禁与自检：`scripts/validate-skills.js`、`scripts/self-check.js`
- 抓取缓存：`.cache/web/*.txt`（默认不提交）
- 长跑状态：`runs/<run-id>/state.json`、`runs/<run-id>/crawl_state.json`、`runs/<run-id>/crawl_log.jsonl`（默认不提交）
- 候选与覆盖率：`runs/<run-id>/candidates.jsonl`、`runs/<run-id>/extractor_state.json`、`runs/<run-id>/metrics.json`、`runs/<run-id>/metrics_log.jsonl`
- 网站构建产物：`website/dist/index.json` + 静态资源
- 验证记录：`docs/verify_log.md`
