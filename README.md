# Skill Repo 项目 Proposal

本仓库把“可执行的 Agent Skill”当作一种可治理的数据资产：每个技能以 `skills/<domain>/<topic>/<slug>/` 目录存储，拆分为 `skill.md`（≤12 步 SOP + Verification + Safety + Sources）、`library.md`（可复制的最小块）、`metadata.yaml`（索引/分级/过滤），并将来源证据与合规信息落到 `reference/`（每条来源记录 URL、License、抓取指纹 sha256/bytes/cache）。生成侧以 `agents/` 提供可长跑的抓取与候选生成链路：来源通过 `agents/configs/sources.yaml` 注册、`agents/configs/<domain>.yaml` 约束 allowlist/denylist；crawler 把抓取队列与每个 URL 的状态写入 `runs/<run-id>/crawl_state.json`（日志 `crawl_log.jsonl`），raw snapshot 缓存在 `.cache/web/`；extractor 从快照抽取 headings 形成 `runs/<run-id>/candidates.jsonl`；orchestrator 用 `--loop` 循环调度并在 `runs/<run-id>/metrics.json`/`metrics_log.jsonl` 输出吞吐与覆盖指标。合并门禁由 `node scripts/validate-skills.js --strict` 在 CI 强制执行（结构、引用绑定 `[[n]]`、来源域名策略、license 字段、可选原文拷贝审计），写入与发布侧提供 `scripts/git-automation.js` 的安全分支推送与 `scripts/build-site.js --out website/dist` 生成 `website/dist/index.json` 供网站/CLI/插件统一检索。这个组合解决了传统 prompt/脚本库常见的“不可治理（格式漂移/重复膨胀）、不可复现（无证据链/无法回归）、不可扩张（缺长跑队列与覆盖指标）、不可合规（license 不可审计）”问题。

### Repo 运行历程图（从来源 → 生成 → 门禁 → 发布）

```text
agents/configs/sources.yaml + agents/configs/<domain>.yaml
  - seeds + refresh + allow/deny domains
  v
agents/orchestrator/run.js --loop        (cycle scheduler)
  - metrics: runs/<run-id>/metrics.json + metrics_log.jsonl
  |
  +--> agents/crawler/run.js
  |      - raw cache: .cache/web/<url-sha>.txt
  |      - state:     runs/<run-id>/crawl_state.json
  |      - log:       runs/<run-id>/crawl_log.jsonl
  |
  +--> agents/extractor/run.js
  |      - candidates: runs/<run-id>/candidates.jsonl
  |      - state/log:  runs/<run-id>/extractor_state.json + extractor_log.jsonl
  |
  +--> agents/runner/run.js (optional; --generate-max-topics)
         - outputs: skills/<domain>/<topic>/<slug>/
           - skill.md + library.md + metadata.yaml + reference/*
         - state: runs/<run-id>/state.json

skills/**  --> node scripts/validate-skills.js --strict  (CI gate)
  |
  +--> node scripts/git-automation.js --execute          (commit/push to branch)
  |
  +--> node scripts/build-site.js --out website/dist
         - website/dist/index.json   --> website/ + cli/ + plugin/chrome/
```

## Q1–Q6：实现与证据（可复现命令 + 产物路径）

下面我按你 6 个问题逐条回答。每条都给出 **可复现命令** 与 **具体产物路径**（你可以直接打开文件核对），不靠口头背书。

快速入口（推荐先跑一遍再看细节）：

```bash
# 一键回归（不需要联网）
node scripts/self-check.js --skip-remote

# 对 repo skills/ 做严格门禁（结构/引用/来源域名/License 字段等）
node scripts/validate-skills.js --strict
```

更多目录与模块说明：`docs/repo_inventory.md`。

### 1 - 我们的 repo 架构跟其他几个开会的时候看到的 repo 一样吗？如果有区别，是为什么这样改呢？

结论：不完全一样；但“技能内容组织”理念一致（**每个 skill 一个目录 + progressive disclosure**）。本 repo 比很多上游 repo 多出来的是：**严格门禁 + 长跑抓取/候选生成 + 安全 git 自动化 + 网站/CLI/插件分发**，目的是支撑规模化运营（不是一次性脚本）。

你开会提到的内容库/基准 repo 是：

- https://github.com/anthropics/skills
- https://github.com/agentskills/agentskills
- https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
- https://github.com/K-Dense-AI/claude-scientific-skills

对齐这些 repo（以它们各自 README/目录结构为准）：

| Repo | 角色定位 | 结构例子（具体路径） | 许可/合规要点（要点） |
| --- | --- | --- | --- |
| [`anthropics/skills`](https://github.com/anthropics/skills) | 示例 skills 库 + spec/template + Claude 插件打包 | `skills/webapp-testing/SKILL.md` + `scripts/` + `examples/`（该 skill 目录里还有 `LICENSE.txt`） | README 明确 “open source 与 source-available 并存”（例如 `skills/docx|pdf|pptx|xlsx` 是 source-available）。因此“吃库”必须 **per-skill/per-file** 记录 license 并可阻断。 |
| [`agentskills/agentskills`](https://github.com/agentskills/agentskills) | Agent Skills 标准/文档/参考 SDK（更偏规范基准线） | `skills-ref/`（含 `LICENSE`=Apache-2.0、`src/`、`tests/`）+ `docs/`（规范与文档） | 更像“标准/SDK”；对接时关注的是 `SKILL.md` 规范与 `references/` 约定。 |
| [`muratcankoylan/Agent-Skills-for-Context-Engineering`](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) | context engineering 主题 skills 库 | `skills/context-compression/SKILL.md` + `references/` + `scripts/` | 根目录 `LICENSE`=MIT（整体相对容易做 reference-only ingest）。 |
| [`K-Dense-AI/claude-scientific-skills`](https://github.com/K-Dense-AI/claude-scientific-skills) | 科研方向 skills 库（含插件/文档） | `scientific-skills/biopython/SKILL.md` + `references/` | 根目录 `LICENSE.md`=MIT（整体相对容易做 reference-only ingest）。 |

#### 1.1 这些 repo 的 skills “具体怎么存”（目录树对比，直观看差异）

本 repo（你现在这个仓库）的 skills 存放方式：

```text
skills/<domain>/<topic>/<slug>/
  skill.md
  library.md
  metadata.yaml
  reference/
    sources.md
    troubleshooting.md
    edge-cases.md
    examples.md
    changelog.md
```

一个真实例子（可直接打开）：

```text
skills/linux/filesystem/find-files/
  skill.md
  library.md
  metadata.yaml
  reference/
    sources.md
    troubleshooting.md
    edge-cases.md
    examples.md
    changelog.md
```

`anthropics/skills` 的 skills 存放方式（示例：`webapp-testing`）：

```text
anthropics/skills/
  skills/
    webapp-testing/
      SKILL.md
      LICENSE.txt
      scripts/
      examples/
  spec/
  template/
  .claude-plugin/
```

`agentskills/agentskills`（它更偏“规范/SDK”，不是主要内容库）结构：

```text
agentskills/agentskills/
  docs/          # 标准文档
  skills-ref/    # reference SDK / validator
    LICENSE      # Apache-2.0
    src/
    tests/
  .claude/        # Claude/Agent 的相关配置（依 repo 实际为准）
```

`muratcankoylan/Agent-Skills-for-Context-Engineering` 的 skills 存放方式（示例：`context-compression`）：

```text
Agent-Skills-for-Context-Engineering/
  skills/
    context-compression/
      SKILL.md
      references/
      scripts/
  template/
  .claude-plugin/
```

`K-Dense-AI/claude-scientific-skills` 的 skills 存放方式（示例：`biopython`）：

```text
claude-scientific-skills/
  scientific-skills/
    biopython/
      SKILL.md
      references/
  docs/
  .claude-plugin/
  LICENSE.md
```

直观看到的差距（为什么本 repo 会“长这样”）：

- **taxonomy 深度不同**：上游多是 `skills/<skill-name>/...`；本 repo 是 `skills/<domain>/<topic>/<slug>/...`（为了把 10 万级内容做成可检索、可分 domain 运营、可分片跑 bot）。
- **分发需要的文件不同**：本 repo 额外有 `library.md`（一键复制）+ `metadata.yaml`（构建索引/过滤/分级）；上游通常把 metadata 放在 `SKILL.md` 的 YAML frontmatter。
- **引用目录命名不同**：上游更常见 `references/`；本 repo 目前是 `reference/`（validator/生成器都按 `reference/` 强制）。如果要最大化生态兼容，可以加转换层输出 `references/` 或 `SKILL.md`。

主要差异与原因（本 repo 相对更偏“可治理/可审计/可分发”的工程形态）：

- **本 repo 是“技能数据集 + 工具链 + 分发面”一体**：`skills/`（数据集）+ `agents/`/`scripts/`（生成/抓取/门禁/长跑）+ `website/`/`cli/`/`plugin/`（网站/CLI/插件分发）。很多上游 repo 只覆盖其中一段。
- **技能格式选择 `skill.md` + `library.md` + `metadata.yaml` + `reference/`**（见 `docs/skill-format.md`、`docs/taxonomy.md`）：
  - `skill.md` 用于 SOP（Steps<=12、含验证/风险/引用）。
  - `library.md` 用于“最小可复制块”（给网站/插件一键复制）。
  - `metadata.yaml` 提供机器可读索引字段（用于构建 `website/dist/index.json`）。
  这么拆的原因是：要同时满足“高质量可读”与“机器可检索/可分发”。
- **更强的门禁与证据链**（避免“机器人胡编/侵权/链接失效”）：`node scripts/validate-skills.js --strict` 会校验章节结构、Steps<=12、Sources>=3、步骤级引用绑定、来源域名 allow/deny、以及 `reference/sources.md` 的 `License:` 字段；可选 `--require-no-verbatim-copy` 做疑似大段原文拷贝审计。

> 兼容性说明（很具体）：上游 repo 普遍是 `SKILL.md` + `references/`；本 repo 目前是 `skill.md` + `reference/`，并额外拆了 `library.md` 与 `metadata.yaml` 来支撑分发与索引。如果要对齐 Agent Skills 生态，建议新增一个 exporter/转换层输出 `SKILL.md`（不影响现有 `website/cli/plugin` 的消费格式）。

#### 例子：本 repo 的一个 skill 目录“长什么样”

以 `linux/filesystem/find-files` 为例：`skills/linux/filesystem/find-files/`

```text
skills/linux/filesystem/find-files/
  skill.md
  library.md
  metadata.yaml
  reference/
    sources.md
    troubleshooting.md
    edge-cases.md
    examples.md
    changelog.md
```

其中 `metadata.yaml` 是机器索引入口（示例字段）：

```yaml
id: linux/filesystem/find-files
domain: linux
level: bronze
risk_level: medium
```

#### 例子：分发面为什么需要 `library.md` + `metadata.yaml`

- 网站/插件/CLI 都依赖“可机器索引的总表”来做检索：`website/dist/index.json`
- 这个 index 是由脚本从 `skills/**` 构建的：

```bash
node scripts/build-site.js --out website/dist
```

`website/dist/index.json` 的头部字段示例（会随内容变化）：

```json
{
  "skills_count": 38,
  "skills": [
    { "id": "linux/filesystem/find-files", "level": "bronze", "risk_level": "medium" }
  ]
}
```

### 2 - 这个架构是否同时支持网页端的 integration 和本地的开源模型？

这个 repo 把 “Skill 内容格式（`skills/`）” 与 “分发（`website/`/`cli/`/`plugin/`）” 与 “生成/提质（`agents/`）” 解耦，因此可以同时覆盖：

- 网页端检索与分发：构建后产出 `website/dist/index.json`，网站/CLI/插件统一读取（见 2.1）。
- 本地开源模型参与生成/提质：`agents/run_local.js` 支持 `mock|ollama|openai`，可在本机用 Ollama 做 rewrite（见 2.2）。
- 第三方 integrations（Slack/Notion 等）内容生产：通过 “sources registry → crawler/extractor 产候选 → writer/runner 生成 skills” 的流水线接入；目前 repo 内置 domain 示例是 `linux`/`productivity`，新增 integrations 只需要补一个 domain 配置 + sources registry（例子见 2.3）。

> 安全边界：本 repo 不做“登录网页/代操作账号”的浏览器自动化（见 `SAFETY.md`）。

#### 2.1 网页端（网站/插件/CLI）怎么跑（例子）

构建索引：

```bash
node scripts/build-site.js --out website/dist
```

产物：

- `website/dist/index.json`（搜索索引 + 每条 skill 的可渲染内容）
- `website/dist/index.html`、`website/dist/app.js`、`website/dist/style.css`

本地预览：

```bash
node scripts/serve-site.js --dir website/dist --port 4173
# 打开 http://127.0.0.1:4173/ 或 http://127.0.0.1:4173/index.json
```

CLI 例子：

```bash
node cli/skill.js search find
node cli/skill.js show linux/filesystem/find-files --file library
```

Chrome 插件（`plugin/chrome/`）例子：

- `plugin/chrome/manifest.json` 已包含 `http://127.0.0.1/*` host permission（配合本地 `serve-site` 直接读 `index.json`）。
- 插件会从 `<baseUrl>/index.json` 读取 `library_md`，用户点击即可复制。

#### 2.2 本地开源模型（Ollama）怎么接（例子）

入口：`agents/run_local.js` + `agents/llm/index.js`（provider 支持 `mock|ollama|openai`）。

- 离线可复现（mock，适合 CI/自检）：

```bash
rm -rf /tmp/skill-llm-out
node agents/run_local.js \
  --domain linux --topic filesystem/find-files \
  --out /tmp/skill-llm-out --overwrite --capture \
  --llm-provider mock --llm-fixture agents/llm/fixtures/rewrite.json
node scripts/validate-skills.js --skills-root /tmp/skill-llm-out --strict
```

- 本地开源模型（Ollama）示例（需要你本机已启动 `ollama serve` 并拉好模型）：

```bash
rm -rf /tmp/skill-ollama-out
node agents/run_local.js \
  --domain linux --topic filesystem/find-files \
  --out /tmp/skill-ollama-out --overwrite --capture \
  --llm-provider ollama --llm-model qwen2.5:7b --llm-base-url http://127.0.0.1:11434
```

#### 2.3 第三方 integrations（以 Slack docs 为例，配置即接入）

1) 在 `agents/configs/sources.yaml` 增加一个 source（抓取入口 + 刷新策略 + 合规备注）：

```yaml
- id: integrations_slack_docs
  type: http_seed_crawl
  domain: integrations
  seeds:
    - https://api.slack.com/
  refresh:
    mode: ttl
    interval: 7d
  purpose: primary
  allowlist: true
  license_policy: "manual_review_per_page (record License field in sources.md; no verbatim copy)"
```

2) 新建 `agents/configs/integrations.yaml`（最小可运行形态：白名单 + source 选择；topics 可先空或先人工挑选）：

```yaml
domain: integrations
owners: []

sources:
  primary:
    - integrations_slack_docs

source_policy:
  allow_domains:
    - slack.com
  deny_domains: []

seeds: []
topics: []
```

3) 运行抓取 + 候选生成（长跑用 `--loop`）：

```bash
node agents/orchestrator/run.js \
  --domain integrations --run-id integrations-weekly \
  --loop --crawl-max-pages 200 --crawl-max-depth 2 --extract-max-docs 200
```

产物会落在 `runs/integrations-weekly/`（例如 `crawl_state.json`、`candidates.jsonl`、`metrics.json`）；`candidates.jsonl` 是后续生成 integrations skills 的输入队列。

> 注意：`--capture` 会抓取公开来源写入证据（需要联网）；LLM 这一步可以本地跑（Ollama）或离线固定输出（mock）。

### 3 - 机器人生成的 markdown 内容质量是否确认合理、精炼、高质量？生成过程是不是每一个都小心地检查过 license 了？

这里把“质量”拆成两层：①结构与证据（自动化硬门禁）；②内容正确性与精炼度（靠模板约束 + 来源绑定 + 抽检/评审迭代）。license 同理：先把证据链与阻断点做成强制流程，再逐步把“可自动判定的部分”工程化。

- CI 硬门禁：`.github/workflows/ci.yml` 会跑 `node scripts/validate-skills.js --strict`，对 `skills/**` 强制检查结构、Steps<=12、Sources>=3、步骤级引用绑定（`[[n]]`）、来源域名 allow/deny、`reference/sources.md` 的抓取指纹（bytes/sha256/cache）与 `License:` 字段。
- 原文拷贝审计：`node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web` 会把产物与抓取快照做近似重复检测；对应自动化入口见 `.github/workflows/audit-capture.yml`。
- 提质（可选）：`agents/run_local.js` 支持 `mock|ollama|openai`，可以把“机器初稿”rewrite 成更精炼的 SOP，然后再过同一套 validator（例子见 2.2）。

#### 3.1 严格门禁到底检查了什么（非常具体）

命令：

```bash
node scripts/validate-skills.js --strict
```

它会对 `skills/**` 里每个含 `metadata.yaml` 的 skill 目录做检查，包含但不限于：

- **目录与必备文件**（缺一个就 fail）：
  - `skill.md`、`library.md`、`metadata.yaml`
  - `reference/sources.md`、`reference/troubleshooting.md`、`reference/edge-cases.md`、`reference/examples.md`、`reference/changelog.md`
- **skill.md 结构**：必须包含以下 `##` 标题：
  - `Goal` / `When to use` / `When NOT to use` / `Prerequisites` / `Steps` / `Verification` / `Safety & Risk` / `Troubleshooting` / `Sources`
- **Steps 规则**：必须是编号列表；且 **Steps <= 12**
- **Sources 数量**：`skill.md` 的 `Sources` 章节至少 3 条（形如 `- [1] ...`）
- **步骤级引用绑定（strict）**：
  - `Steps` 里必须出现 `[[n]]` 引用
  - **任何包含命令的 step 行**（含反引号代码块）必须以 `[[n]]` 结尾（避免“命令无出处”）
- **来源证据与 license（strict）**：`reference/sources.md` 的每个 `## [n]` block 必须包含：
  - `- URL:`（且必须是 http/https）
  - `- License:`（不能为空/不能是 TODO）
  - `- Fetch cache: hit|miss`、`- Fetch bytes: <n>`、`- Fetch sha256: <64hex>`（抓取指纹）
- **来源域名策略（strict）**：`reference/sources.md` 里的 URL 必须符合 `agents/configs/<domain>.yaml` 的 `source_policy.allow_domains/deny_domains`

#### 3.2 “合理、精炼、高质量”怎么用例子证明（例子）

以 `skills/linux/filesystem/find-files/skill.md` 为例，Steps 是“短 SOP + 每步有出处”，例如：

```md
1. 先做 dry-run：`find <root> -type f -name '<pattern>' -print`（只打印不修改）[[1]]
7. 组合条件：`find . \( -name '*.jpg' -o -name '*.png' \) -type f -print`[[1][2]]
8. 写操作优先 `-exec ... {} +`，并要求交互确认：`find . -name '*.tmp' -type f -exec rm -i {} +`[[1][2][3]]
```

对应的 `skills/linux/filesystem/find-files/reference/sources.md` 会把每条来源写成“摘要 + 支撑 Steps + License + 抓取指纹”，例如：

```md
## [1]
- URL: https://man7.org/linux/man-pages/man1/find.1.html
- Summary: find(1) 选项与表达式（-name/-type/-mtime/-size/-maxdepth/-exec 等）。
- Supports: Steps 1-8
- License: unknown
- Fetch cache: hit
- Fetch bytes: 109430
- Fetch sha256: 834fca2923ce9fe3...
```

抓取缓存（用于审计/复现）默认写到 `.cache/web/`，按 URL 哈希命名，例如该 URL 的缓存文件会是：`.cache/web/a43c2ddf19e3ceaa.txt`（默认不提交 git）。

#### 3.3 License 记录与审计（具体）

- 当前实现要求每条来源都有：`URL` + `License:` + 抓取指纹（sha256/bytes/cache），并且用 `agents/configs/<domain>.yaml` 的 allow/deny 域名策略做第一道“越界阻断”。
- 对于“license 自动判定（允许/禁止/需复核）”，需要把一份明确的 policy（白/黑/灰）落成机器可执行规则；目前仓库里把这件事作为待补齐的工程项（见 `docs/mohu.md` 的 Amb-002）。

如果你希望把“疑似大段原文拷贝”作为硬门禁（强烈建议），额外启用：

```bash
node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web
```

### 4 - 我们希望部署多个能连续运行数天到数星期的机器人：数据源够大且稳定吗？会不会跑俩小时就结束？我们至少要吃掉现有的所有这些 library 的内容。

“不会跑俩小时就结束”的关键是：队列与进度必须落盘，并且由调度器持续补货/刷新。本 repo 的最小闭环是：`agents/configs/sources.yaml`（来源注册）→ `agents/crawler/`（DocItem 状态落盘）→ `agents/extractor/`（候选落盘）→ `agents/orchestrator/`（循环调度 + 指标落盘）。

- 常驻运行：`agents/orchestrator/run.js` 的 `--loop` 会在 BUSY/IDLE 之间循环（IDLE 也保留 state，等待下一次 refresh/discover）。
- 是否“两小时就结束”：只取决于运行方式与上限参数（例如 `--crawl-max-pages`/`--extract-max-docs`/`--max-cycles`/是否启用 `--loop`）。
- 多机器人并行：推荐按 domain 或按 source 分片，并给每个机器人独立 `--run-id`（避免并发写同一份 `runs/<run-id>/*.json`）。如果需要跨机器共享队列/lease，下一步是把 state/queue 落到 DB（蓝图见 `agents/orchestrator/README.md`）。

#### 4.1 数据源是否“够大且稳定”（例子）

数据源入口统一登记在：`agents/configs/sources.yaml`（Tier1: 官方/权威 docs；Tier0: 上游 skills/spec，reference-only）。

例如 `linux_tier1_web`（Tier1 seeds）包含：

- `https://man7.org/linux/man-pages/index.html`
- `https://www.gnu.org/software/coreutils/manual/coreutils.html`
- `https://wiki.archlinux.org/`
- `https://pubs.opengroup.org/onlinepubs/9699919799/`

刷新策略（避免频繁重复抓、同时支持“几周跑一次更新”）：`sources.yaml` 里为每个 source 配 `refresh.mode: ttl` + `refresh.interval: 7d/14d/...`；orchestrator 会把这个 interval 转成 `--cache-ttl-ms` 传给 crawler。

#### 4.2 “不会跑俩小时就结束”的关键：状态机 + 断点续跑 + 永续调度（例子）

1) crawler（URL 发现/抓取/落盘）

- 命令（一次抓一批）：

  ```bash
  node agents/crawler/run.js --domain linux --run-id linux-crawl-demo --max-pages 50 --max-depth 2
  ```

- 产物：
  - `runs/linux-crawl-demo/crawl_state.json`（队列 + 每个 URL 的 doc 状态）
  - `runs/linux-crawl-demo/crawl_log.jsonl`（每个 URL 一行日志，可审计）
  - `.cache/web/*.txt`（raw snapshot 缓存，默认不提交 git）

- doc 状态机字段（真实字段名；值仅示意）：

  ```json
  {
    "url": "https://man7.org/linux/man-pages/man1/find.1.html",
    "state": "FETCHED",
    "discovered_at": "2026-01-15T00:00:00.000Z",
    "fetched_at": "2026-01-15T00:00:01.000Z",
    "attempts": 1,
    "fetch": { "cache": "hit", "status": 200, "bytes": 109430, "sha256": "834fca29...", "cache_file": "a43c2ddf19e3ceaa.txt" }
  }
  ```

  如果 URL 不在 allowlist，会在日志里看到（真实字段名；值仅示意）：

  ```json
  {"ok":false,"doc_state":"BLOCKED","error":"blocked by source_policy","url":"https://example.com/outside"}
  ```

2) extractor（DocItem → TopicCandidates，断点续跑）

- 命令：

  ```bash
  node agents/extractor/run.js --domain linux --run-id linux-crawl-demo --max-docs 50
  ```

- 产物：
  - `runs/linux-crawl-demo/candidates.jsonl`（每行一个 candidate）
  - `runs/linux-crawl-demo/extractor_state.json`（记录 URL+sha 已处理，用于长期迭代）
  - `runs/linux-crawl-demo/extractor_log.jsonl`（处理日志）

- candidate 行结构示例（真实字段名；值仅示意）：

  ```json
  {"id":"cand_1a2b3c4d5e6f","domain":"linux","kind":"doc_heading","title":"NAME","level":2,"source":{"url":"https://...","fetched_sha256":"...","cache_file":"..."}}
  ```

3) orchestrator（crawler + extractor (+ runner) 的循环调度 + 指标）

- 命令（真正“几天/几周常驻”就是 `--loop`）：

  ```bash
  node agents/orchestrator/run.js \
    --domain linux --run-id linux-orch-weekly \
    --loop --crawl-max-pages 200 --crawl-max-depth 2 --extract-max-docs 200 \
    --cycle-sleep-ms 600000
  ```

- 产物（都在 `runs/linux-orch-weekly/`）：
  - `metrics.json`（最新快照）
  - `metrics_log.jsonl`（每个 cycle 追加一行，适合做 dashboard）
  - 以及 crawler/extractor 的所有落盘文件（`crawl_state.json`、`candidates.jsonl` 等）

#### 4.3 “至少吃掉现有所有这些 library”——目前做到哪、还缺哪（不含糊）

- 已做到：`agents/configs/sources.yaml` 已登记你提到的上游 repo（Tier0，reference-only）：
  - `upstream_anthropic_skills` → https://github.com/anthropics/skills
  - `upstream_agentskills_spec` → https://github.com/agentskills/agentskills
  - `upstream_context_engineering_skills` → https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
  - `upstream_claude_scientific_skills` → https://github.com/K-Dense-AI/claude-scientific-skills
- 下一步：把这些 GitHub repos 真正接入“discover/fetch/parse/extract”流水线（让 crawler/extractor 能像处理 docs 站点一样处理 repo 文件）。
  - 目前已有 adapter 雏形：`agents/adapters/github_repo.js`（只支持本地目录扫描）、`agents/adapters/sitemap.js`、`agents/adapters/openapi.js`、`agents/adapters/manpage.js`（占位）。
  - 所以现阶段“长跑闭环”主要覆盖 `http_seed_crawl`（公开 docs 站点）；repo 型 sources 需要下一步工程化（远端拉取/增量/解析）。

### 5 - 机器人的自动 git push 是否经过了调试确保没问题？

Git 自动化入口是 `scripts/git-automation.js`：默认 dry-run（只打印计划），显式 `--execute` 才会在分支上 commit 并 push。`node scripts/self-check.js --skip-remote` 会在临时 git repo + 本地 bare remote 中做回归，覆盖 dry-run 与分支 push 的关键路径。

目前自动化覆盖的是 “push branch”；PR 创建可用 GitHub UI 或 `gh pr create` 补齐（如果需要完全自动化，可在 workflow/脚本层对接 GitHub API 或 `gh`）。

#### 5.1 这件事在代码里具体怎么做（例子）

- 入口脚本：`scripts/git-automation.js`
- 设计要点（都能在脚本输出里看到）：
  - **默认 dry-run**：不 checkout/commit/push，只打印“将要提交哪些文件”
  - 分支名校验：用 `git check-ref-format` 拒绝非法分支名
  - 执行模式才会：`checkout -b` → `git add -- <paths>` → `git commit -m <msg>` → `git push -u <remote> <branch>`
  - 默认会尝试切回起始 ref（避免把开发者工作区留在 bot 分支）
  - push 失败可重试（`--retries` / `--retry-delay-ms`）

#### 5.2 你自己怎么在真实仓库里跑（例子）

- 先看计划（dry-run 是默认行为）：

```bash
node scripts/git-automation.js --paths skills --branch bot/linux/demo --message "chore: bot update"
```

- 确认无误后再执行（会创建/切换分支、commit、push；并默认切回原 ref）：

```bash
node scripts/git-automation.js --paths skills --branch bot/linux/demo --message "chore: bot update" --execute
```

#### 5.3 已有的“自动化调试证据”（例子）

`node scripts/self-check.js --skip-remote` 会在 **临时 git repo + 本地 bare remote** 中验证 dry-run + 分支 push 成功（你运行后输出会包含：`OK   git-automation - dry-run + branch push OK`，详见 `docs/verify_log.md`）。

### 6 - 机器人部署之后会爬取哪里的内容？他们足够多吗？我们接下来如何方便高效地 scale 到足够多的内容上去？

爬取范围完全由配置决定，并且会被 crawler 强制执行（allow/deny + 阻断日志）。当前仓库内置的 domain 配置是 `linux`/`productivity`，因此“默认会爬哪里”非常明确：只会从 `agents/configs/<domain>.yaml` 与 `agents/configs/sources.yaml` 合并出来的 seeds 出发，并且只允许落在 `source_policy.allow_domains` 里的域名。

规模化的关键是把新增来源变成“主要改 YAML”：对 `http_seed_crawl`（公开 docs 站点）已经可以做到；对 repo/sitemap/openapi/manpage 等来源类型，仓库已提供 adapter 雏形，继续把它们接入 orchestrator 的 discover/fetch 即可把覆盖面扩大到更多“可枚举、可增量”的数据源。

#### 6.1 “爬取范围”在 repo 里具体写在哪（例子）

1) domain config：`agents/configs/<domain>.yaml`

以 `agents/configs/linux.yaml` 为例（节选）：

```yaml
source_policy:
  allow_domains:
    - man7.org
    - gnu.org
    - archlinux.org
    - opengroup.org
seeds:
  - https://man7.org/linux/man-pages/index.html
  - https://www.gnu.org/software/coreutils/manual/coreutils.html
```

2) sources registry：`agents/configs/sources.yaml`

- 用于集中管理“Tier1 官方/权威 docs”与“Tier0 上游 repos/spec（reference-only）”。
- orchestrator 会把 domain 的 `sources.primary[]` 对应 source 的 seeds 合并后传给 crawler（因此 scale 的主要工作是加 sources.yaml + 扩 allowlist）。

#### 6.2 crawler 如何强制执行 allow/deny（例子）

- 不在白名单域名的 URL 会被 `BLOCKED`，并写入 `runs/<run-id>/crawl_log.jsonl`（每个 URL 一行）。
- self-check 里有一个本地例子：它启动本地 HTTP server，并在 HTML 里放一个外链 `https://example.com/outside`；crawler 只允许 `127.0.0.1`，因此外链会被阻断（对应 `scripts/self-check.js` 的 “crawler smoke”）。

你也可以手动跑一个“本地 seed + allowlist”例子（需要你先起一个本地 HTTP server）：

```bash
node agents/crawler/run.js --domain linux --run-id local-crawl --seeds http://127.0.0.1:8080/seed --allow-domain 127.0.0.1
```

#### 6.3 怎么“方便高效 scale”到更多内容源（例子）

新增一个来源的最小步骤（只改配置，不改 pipeline）：

1) 在 `agents/configs/sources.yaml` 加一个 source（例：某个 integrations 方向的官方 docs）：

```yaml
- id: integrations_slack_docs
  type: http_seed_crawl
  domain: integrations
  seeds:
    - https://api.slack.com/
  refresh:
    mode: ttl
    interval: 7d
  purpose: primary
  allowlist: true
  license_policy: "manual_review_per_page (record License field; no verbatim copy)"
```

2) 在 `agents/configs/integrations.yaml`（如果你创建了该 domain）里：

- `sources.primary` 加上 `integrations_slack_docs`
- `source_policy.allow_domains` 加上 `slack.com`
- `seeds` 可留空或保留（orchestrator 会优先从 `sources.primary` 取 seeds）

3) 用新的 run-id 跑（多机器人并行时，**每个机器人用独立 run-id**，避免并发写同一份 state）：

```bash
node agents/orchestrator/run.js --domain integrations --run-id integrations-weekly --loop --cycle-sleep-ms 600000
```

> 当前 crawler 是纯 HTML `href=` 发现（不做 JS 渲染/登录站点）。如果来源是 SPA/需要登录，建议改用 sitemap/OpenAPI/或专门 adapter。repo 已放了 adapter 雏形：`agents/adapters/sitemap.js`、`agents/adapters/openapi.js`、`agents/adapters/manpage.js`（部分仍是 scaffolding）。

---





## 0. 背景与动机（为什么做）
当前大量“教程/提示词/脚本”类仓库面临三类不可持续问题：

1. **不可治理**：内容随贡献者堆叠，缺少统一格式与门槛，质量快速坍塌。
2. **不可更新**：软件版本、链接、最佳实践迭代快，人工维护成本指数上升。
3. **不可复现**：缺少验证步骤与可追溯来源，易产生误导与合规风险。

本项目的核心定位不是“再做一个教程库”，而是做一个 **可扩张的技能标准体系**：  
- **标准**：Skill 的格式、元数据、引用规则、风险边界、质量分层、生命周期机制  
- **工具链**：方向机器人自动生成 → 校验 → 去重 → 提 PR → 人审合并 → 官网/CLI/插件发布  
- **分发**：官网（搜索/浏览/复制）+ CLI（检索/本地索引/可选执行）+ Web 插件（传播入口）  
- **公信力来源**：透明来源 + 可复现评测（而非依赖某个 benchmark 名字）

---

## 1. 项目定位与总体架构
### 1.1 定位升级：Repo + 标准 + 工具链 + 分发 + 可复现评测
你要交付的是一个可以持续扩张的系统，而不是一次性内容堆积。

**系统组件**：
- **Skills 内容层**：`skills/<domain>/<topic>/<slug>/...`
- **共性方法层（Patterns）**：跨领域复用的“提示词/工具使用/安全策略/评测方法”
- **Agents 工具链层**：crawler/extractor/writer/validator/pr_submitter + configs
- **治理与生命周期层**：质量分层、升级/降级、过期检测、stale/归档
- **分发层**：官网 + CLI + 插件
- **Eval 层**：容器化/固定脚本的任务集与报告（每次 release 发布）

### 1.2 设计不变量（必须长期成立）
- **每个 skill 一个文件夹**，并且格式强制一致（机器可读、可检索、可验证、可组合）。
- `skill.md` **高度凝练**：主流程覆盖 80% 场景，Steps **<= 12**；所有长内容下沉到 `reference/` 或 `/patterns/`。
- **关键步骤必须可追溯**：命令/参数/关键决策 → 必须做步骤级引用绑定（Step → Source）。
- **机器人只提 PR，不直推 main**；合并必须经过门禁（Validator + 人审策略）。
- **现实世界/不可逆操作默认不自动执行**（只提供 SOP + 核对清单 + 强确认机制）。
- **公信力来自可复现**：gold skills 与 eval 报告必须可复现、可对比、可回归。

---

## 2. 目标与成功标准（可量化）
### 2.1 里程碑
#### M0（2 天内，必须达成）
**硬 DoD（Definition of Done）**：
1. Repo 骨架：README / LICENSE / docs / workflows / 贡献指南 / 安全边界文件齐全  
2. Skill 标准 v1 定稿（含步骤-引用绑定规则）  
3. Bot MVP：至少 1 个方向可自动生成 PR（端到端跑通）  
4. Validator MVP：格式/链接/引用/重复/风险词等校验可作为合并门禁  
5. Skills ≥ 50：至少 **20 silver、5 gold**，其余 bronze  
6. 官网 MVP：可搜索、可复制 library block、显示质量等级与来源  
7. CLI MVP：search/open/copy + 本地索引  
8. 插件 MVP：检索/复制/跳转（不做自动执行）  
9. 发布 v0.1-alpha：Demo GIF + Roadmap + 自动化徽章（CI/link-check/site build）

#### M1（1-2 个周，确保“最坏也留痕”）
- Skills ≥ 2,000（silver/gold 占比上升）  
- 固定周更节奏：每周 release + 变更日志 + eval 报告（哪怕小步）  
- 社区治理稳定：PR 自动评分，低分 PR 不消耗 maintainer 时间  
- 生命周期机制运行：link-check、stale、降级/归档流程有效

#### M2（1 个月，冲 10 万级）
- 依靠 **参数化/组合化/去重** 扩量，而不是堆重复文档  
- 方向 bot 矩阵化（统一框架 + config 驱动）  
- Eval 与质量治理成为事实标准（可被他人复用/对比）

### 2.2 传播目标（对外叙事）
- 30 秒让人理解差异化：**机器人产出 + 质量分层 + 可复现验证 + 官网/CLI/插件完整链路**  
- 即使不爆火，也能留下系统级工程资产：CI、站点、机器人 PR 轨迹、可复现 eval 报告

---

## 3. Skill 标准 v1（强制结构 + 步骤-引用绑定）
### 3.1 `skill.md` 强制结构（缺一不可）
1. **Goal**（一句话目标）  
2. **When to use / When NOT to use**（适用/禁用场景）  
3. **Prerequisites**（环境/权限/工具/输入）  
4. **Steps（<= 12）**（主流程，必须可执行、可验证）  
5. **Verification**（如何确认成功 + 期望输出/状态）  
6. **Safety & Risk**（不可逆/隐私/凭证/支付提交等警告与确认）  
7. **Troubleshooting pointer**（指向 `reference/troubleshooting.md`）  
8. **Sources（>= 3）**（公开可追溯来源）

### 3.2 步骤-引用绑定（解决“机器人胡编”）
**规则**：凡是属于“关键步骤”的内容必须绑定来源编号：  
- 命令、参数、配置项、关键判断条件、关键输出解释  
- 绑定方式：在 Steps 的 step 行尾标注 `[[n]]`（可多源 `[[1][2]]`；含命令的 step 在严格模式下必须以 `[[n]]` 结尾）

**来源记录规范**：`reference/sources.md` 必须包含  
- URL  
- 访问日期  
- 摘要（用自己的话）  
- 支撑的步骤编号（Step mapping）  
- 允许少量关键摘录（避免大段复制粘贴）

### 3.3 三种 Skill 形态（支持 10 万级扩张）
1. **Atomic（原子）**：单目标、可测试、可复用  
2. **Composite（组合）**：引用多个 Atomic，不重复写细节（通过链接/引用）  
3. **Parameterized（参数化）**：同模板 + 参数覆盖 OS/版本/工具差异，减少重复

---

## 4. 仓库结构（完整结构 + 每一层含义）
> 目标：结构专业、可扩张、可治理、可自动化、可分发。

### 4.1 顶层目录结构（建议最终形态）
```text
/
  README.md
  LICENSE
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  SECURITY.md
  SAFETY.md
  CHANGELOG.md

  /docs/
    index.md
    taxonomy.md
    skill-format.md
    prompts.md
    governance.md
    lifecycle.md
    faq.md
    budget.md

  /skills/
    /linux/
    /web/
    /cloud/
    /data/
    /productivity/
    /travel/
    /integrations/
    /devtools/

  /patterns/
    prompting/
    rag/
    tool-use/
    evaluation/
    safety/

  /agents/
    /generator/
    /validator/
    /curator/
    /tools/
    /configs/
    /templates/
      /pr/

  /eval/
    /tasks/
      /linux/
      /web/
      ...
    /harness/
    /reports/

  /.github/
    /workflows/
      ci.yml
      lint.yml
      link-check.yml
      build-site.yml
      agent-generate.yml
      eval.yml
    ISSUE_TEMPLATE/
    PULL_REQUEST_TEMPLATE.md

  /website/      # 静态站或 Next.js（可选）
  /cli/
  /plugin/
````

### 4.2 每个 skill 的目录结构（强制标准）

```text
skills/<domain>/<topic>/<skill_slug>/
  skill.md
  library.md
  metadata.yaml
  reference/
    sources.md
    troubleshooting.md
    edge-cases.md
    examples.md
    changelog.md
```

**文件含义**：

* `skill.md`：主流程（<=12 steps）+ 验证 + 风险 + 引用（高度凝练）
* `library.md`：最小可复制块（命令/提示词/检查命令），用于官网/插件“一键复制”
* `metadata.yaml`：机器可读元数据（域、级别、风险、平台、工具、owner、最后验证日期等）
* `reference/`：所有长内容与维护性内容下沉

  * `sources.md`：来源与 step mapping（合规与可信度核心）
  * `troubleshooting.md`：常见错误与修复路径
  * `edge-cases.md`：版本差异/边界条件
  * `examples.md`：长示例（避免污染 skill.md）
  * `changelog.md`：变更记录（可由机器人辅助生成）

### 4.3 `patterns/`（基础方法上提）

将跨技能复用的内容（如通用 RAG prompt、工具使用范式、安全策略、评测套路）集中沉淀在 `/patterns/`，避免每个 skill 重复抄写，保证可维护性与一致性。

---

## 5. 质量分层与生命周期治理（防止仓库腐烂）

### 5.1 质量等级（Level）

* **bronze**：机器人生成，结构完整但待审（允许存在不确定点，必须标注并下沉）
* **silver**：人工审核通过（引用与步骤可信，未必完全实测）
* **gold**：可复现验证（必须有验证记录/最小脚本/输出片段，且能回归）

### 5.2 风险等级（Risk Level）

* **low**：只读/查询/无破坏性操作
* **medium**：可能修改配置/写文件/影响服务但可逆
* **high**：删除/权限变更/服务管理/用户管理/潜在不可逆/安全敏感

### 5.3 升级/降级/归档机制

**升级**：

* bronze → silver：完成人工审核记录（review note + 来源检查 + 步骤绑定校验通过）
* silver → gold：提供可复现验证记录（last_verified + 验证输出/脚本/关键结果）

**自动降级**（生命周期）：

* link-check 大面积失效 / gold 回归失败 / 关键步骤来源不可用 → 自动降级 level 或标记 `stale`
* 长期无人维护 → 归档 `archived`（保留历史但不推荐）

### 5.4 自动化生命周期任务（建议频率）

* **每周**：link-check（全量）+ 报告（坏链清单、受影响技能清单）
* **每月**：版本扫描（高频变化领域可缩短）+ gold 抽样回归验证
* **每次合并/发布**：增量重复检测 + 风险词扫描 + schema 校验

---

## 6. Bot 系统（“不能手写”的规模化生产线）

### 6.1 “一方向一 bot”的组织方式

每个 domain 配一个 bot（或一个 bot 多配置），例：

* `linux-bot`：命令、排障、系统工具
* `web-bot`：浏览器流程（合规边界内）
* `travel-bot`：现实世界流程 SOP（默认不自动执行）
* `integrations-bot`：跨软件集成（Notion/Sheets/Slack 等）
* `cloud-bot`：云平台基础操作
* `productivity-bot`：办公软件工作流
* `data-bot`：数据处理（csv/json/etl）
* `devtools-bot`：git/ci/包管理/环境搭建

### 6.2 Bot 统一框架（组件化）

* **crawler**：搜索/抓取（优先白名单来源：官方文档、man page、发行版文档）
* **extractor**：抽取可执行步骤/命令/验证/风险点/边界条件
* **writer**：按模板生成 `skill.md/library.md/reference/*/metadata.yaml`
* **validator**：格式、引用、链接、重复、风险词、schema
* **pr_submitter**：创建 PR（含变更说明、来源统计、校验结果、风险摘要）

### 6.3 长期运行设计（确保能“跑数天到数星期”）

为避免“跑两小时就结束”，bot 必须具备持久化状态与迭代策略：

**持久化组件**：

* **Source Registry**：数据源注册表（URL、类型、许可、抓取策略、更新时间）
* **Topic Registry**：主题清单与覆盖度（已生成/已审/已验证/待更新）
* **Persistent Queue**：待处理任务队列（支持重试、幂等、断点续跑）
* **Artifact Cache**：抓取内容缓存（用于 replay 与回归、节省成本）
* **Dedup Index**：标题/slug/内容向量/哈希去重索引

**迭代策略**：

* coverage 驱动：优先补齐空白领域、补齐 bronze→silver、补齐 high-risk 的审查
* freshness 驱动：根据来源更新时间/软件版本，触发增量更新
* 失败重试与降级：来源不可达则跳过并记录，不阻塞全局

**并发与容器化**：

* 支持 docker 并发运行多个 bot（每方向一容器/进程）
* 限流与礼貌抓取（遵守 robots.txt/站点政策，优先官方镜像与文档站）
* 幂等写入：同一 topic 多次运行不会产生重复目录或破坏 canonical

### 6.4 本地调试与可观测性（必须可调）

每次运行必须输出（用于 review 与排错）：

* sources 列表 + 每条来源支撑的步骤 mapping
* 关键摘录 trace（少量、合规）
* 不确定点清单（必须下沉到 reference 或标记 bronze）
* validator 结果（通过/失败原因）
* run_id / batch_id / 运行配置摘要

提供本地调试入口：

* `agents/run_local`：对单 topic 生成一次
* fixture 缓存与 replay（无网复现）
* golden tests：标杆主题回归（防止提示词或解析器变更导致质量漂移）

---

## 7. Validator（合并门禁：最低必须项）

Validator 必须至少覆盖以下检查（作为 CI 门禁）：

1. **模板字段齐全**：Goal/Prereq/Steps/Verification/Safety/Sources/Troubleshooting pointer
2. **Steps 上限**：<= 12（超出必须拆分或下沉 reference）
3. **Sources 下限**：>= 3（且为公开可访问来源）
4. **关键步骤引用绑定**：命令/参数/关键决策必须有 `[[n]]`（步骤级引用绑定）
5. **链接可达**：link-check（失败则阻止合并或自动降级/标记）
6. **重复检测**：slug 冲突、标题近似、内容高相似度候选（给出 canonical 建议）
7. **风险词/敏感行为扫描**：触发 `SAFETY_REVIEW` 标签与高风险 reviewer
8. **metadata schema 校验**：字段完整、枚举合法、日期格式正确
9. **版权与复制粘贴风险提示**：检测大段原文（超过阈值提示人工确认）
10. **禁止清单命中**：命中则直接 fail（见 SAFETY.md）

---

## 8. 安全边界（现实世界技能与不可逆操作）

### 8.1 默认策略

* **现实世界流程（如买机票/订酒店）**：默认只提供 SOP 与核对清单，不自动执行、不代替支付/提交。
* **不可逆操作**（删除、权限变更、服务停止、账号变更、生产发布等）：

  * `skill.md` 必须包含强警告与“先预览后执行”步骤
  * CLI/执行框架必须强确认（交互确认或显式 `--yes`）
  * 插件默认只提供复制/跳转，不提供自动执行

### 8.2 SAFETY.md 禁止收录范围（必须写死）

* 绕过风控、欺诈、账号盗取、未授权渗透与漏洞利用、恶意软件、隐私窃取
* 任何鼓励违法/危险行为的操作步骤
* 任何需要用户提供敏感凭证并要求保存/上传的流程（必须提示“不要粘贴密钥到日志/仓库/PR”）

---

## 9. License 与合规策略（更硬的规则）

### 9.1 仓库许可建议

* **代码**：MIT 或 Apache-2.0（二选一，需与学校/团队偏好一致）
* **文档内容**：CC BY 4.0（或 CC BY-SA 4.0，按你们开源策略选择）
* 明确“代码许可 ≠ 内容许可”，并写入 README/NOTICE

### 9.2 内容合规规则

* 禁止纳入付费资料原文、内网资料、不可转载内容
* 每个 skill 必须有 Sources，且关键步骤可追溯
* 只做“总结/抽象/转述”，避免大段复制粘贴
* PR 模板要求贡献者勾选合规声明（来源合法、无侵权、无付费搬运）

### 9.3 上游内容“混入策略”（避免踩坑）

对外部仓库/文档引入时：

* 首选“引用链接 + 摘要 + step mapping”，不直接搬运原文
* 如果遇到“source-available but not open source”或内容许可不清晰：

  * 只保留引用与抽象总结，不纳入原文；必要时直接排除该来源
* 建立 Source Registry 对来源许可做分类管理（allowlist/graylist/blocklist）

---

## 10. 分发层：官网 + CLI + 插件（边界清晰）

### 10.1 官网（增长引擎）

**MVP 功能**：

* taxonomy 导航：domain → topic → skill
* 全文搜索（标题/标签/正文/命令片段）
* skill 页面：渲染 `skill.md` + `library.md` 一键复制 + sources 展示
* 质量标识：gold/silver/bronze + risk_level
* 最近更新/新增列表（制造活跃度与可信度）
* 自动发布：GitHub Actions → GitHub Pages / 静态托管

### 10.2 CLI（主入口）

分阶段：

* v0：`search/open/copy` + 本地索引（sqlite 或 JSON index）
* v1：支持过滤（domain/level/risk/tools/platform）+ 本地离线检索
* v2（可选）：执行框架（shell/playwright）

  * 默认 dry-run
  * high-risk 强确认
  * 禁止保存凭证到仓库或日志

### 10.3 插件（传播入口）

* 最小：检索 + 跳转 + 一键复制 `library.md`
* 暂不提供自动执行（避免安全与责任风险）
* 清晰提示：不可逆行为必须由用户自行确认

---

## 11. 自建 Eval（替代 SkillBench 的公信力方案）

**核心观点**：公信力来自“透明、可复现、可对比”，而不是 benchmark 名字。

### 11.1 Eval 结构

* `eval/tasks/<domain>/...`：任务集（每方向 50–200 起步）
* `eval/harness/`：运行脚本/容器定义/固定环境
* `eval/reports/`：每次 release 输出报告（成功率、失败类型、覆盖度、版本信息）

### 11.2 指标（建议最小集）

* **Success Rate**（完成率）
* **Median Steps**（完成所需步骤数）
* **Failure Taxonomy**（失败类型分布：缺前置、命令错误、版本不兼容、链接失效等）
* **Coverage**（topic 覆盖、gold 占比、风险等级覆盖）
* **Freshness**（last_verified 分布、stale 数量）

### 11.3 与发布绑定

* 每次 release 附带 eval 报告（哪怕先覆盖部分 domains）
* gold skills 回归验证纳入 eval（抽样或全量）

---

## 12. 团队组织与工作流（intern 的正确用法）

### 12.1 角色定义

* **Maintainer**：标准维护、门禁规则、合并决策、路线图
* **Bot Operator**：维护 bot 配置、数据源、topic 列表、运行与成本控制
* **Intern/Reviewer**：review、补引用、实测、提质、维护 domain 边界与主题清单

### 12.2 PR 流程

1. bot 生成/更新 → 提 PR（包含来源统计、validator 结果、风险摘要）
2. CI 门禁：validator + link-check + schema
3. 人审策略：

   * bronze：抽检 + 高风险必审
   * silver：必须审核记录
   * gold：必须有验证记录与复现材料
4. 合并 → 自动更新 changelog → 站点发布 →（可选）跑 eval 并发布报告

---

## 13. 成本与信用额度（OpenAI credit）策略

* `docs/budget.md`：记录 token/抓取/评测成本估算与监控策略
* 早期申请 credit（但工程上 **不依赖单一 provider**）
* 多模型后端/可替换：避免 credit 卡死交付

---

## 14. 10 天冲刺排期（最终版）

* **Day 1–2**：Repo 结构 + 模板 + DoD + CI 门禁 + SAFETY/SECURITY/贡献指南
* **Day 3–4**：1 个方向 bot MVP + validator MVP + PR 流程跑通
* **Day 5**：本地调试 + trace + fixture replay + golden tests
* **Day 6–7**：扩到 5–8 个方向，产出 ≥ 50 skills（分层：20 silver / 5 gold）
* **Day 8**：官网 MVP 发布（搜索/复制/质量标识/来源透明）
* **Day 9**：CLI MVP + Demo GIF（search/open/copy + 索引）
* **Day 10**：插件 MVP（检索/复制/跳转）+ v0.1-alpha release + roadmap

---

## 15. 初始方向（建议先跑起来的 8 个 domains）

1. linux（命令/排障/常用工具）
2. web（浏览器基本流程、下载、表单；不做绕过）
3. productivity（Docs/Sheets/Notion 等基础工作流）
4. integrations（跨软件数据搬运与同步）
5. travel（买机票/订酒店/行程规划：只 SOP + 核对清单）
6. cloud（账号/权限/部署最短路径）
7. data（csv/json/etl 常用处理）
8. devtools（git/ci/包管理/环境搭建）

---

# 附录 A：`skill.md` 模板（强制）

```md
# <Skill Title>

## Goal
- <One sentence goal>

## When to use
- <Use cases>

## When NOT to use
- <Anti-cases / risks>

## Prerequisites
- Environment:
- Permissions:
- Tools:
- Inputs needed:

## Steps (<= 12)
1. ...[[1]]
2. ...[[2]]
3. ...[[1][3]]

## Verification
- What to check:
- Expected output / state:

## Safety & Risk
- Irreversible actions:
- Privacy/credential handling:
- Payment/submit warnings:
- Confirmation requirement (if any):

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] ...
- [2] ...
- [3] ...
```

---

# 附录 B：`library.md` 模板（复制区）

````md
# Library (Copy/Paste)

## Minimal commands
```bash
# command 1
# command 2
````

## Minimal prompt (if applicable)

```text
<short, reusable prompt>
```

## Quick checks

```bash
# verification commands
```

````

---

# 附录 C：`metadata.yaml` 模板（机器可读）
```yaml
id: <domain>/<topic>/<skill_slug>
title: "<Skill Title>"
domain: <linux|web|cloud|travel|data|productivity|integrations|devtools>
topic: <topic>
level: <bronze|silver|gold>
risk_level: <low|medium|high>
platforms: [linux, macos, windows, web]
tools: [bash, git, chrome, ...]
tags: [rag, automation, troubleshooting]
aliases: []
owners: ["@handle1", "@handle2"]
last_verified: "YYYY-MM-DD"   # silver/gold recommended; required for gold
````

---

# 附录 D：`reference/sources.md` 模板（合规与可信度核心）

```md
# Sources

## [1] <Title>
- URL: <...>
- Accessed: YYYY-MM-DD
- Summary: <your own words, short>
- Supports steps: 2, 3
- Key excerpt (optional, short): "<short excerpt>"

## [2] ...
```

---

# 附录 E：Domain 配置（`agents/configs/<domain>.yaml` 示例）

```yaml
domain: linux
owner: "@domain-owner"
scope:
  include:
    - "filesystem"
    - "process"
    - "network"
  exclude:
    - "malware"
    - "unauthorized access"
source_policy:
  allowlist:
    - "man7.org"
    - "gnu.org"
    - "docs.*"
  require_manual_review_domains:
    - "blog.*"
generation_policy:
  max_steps: 12
  min_sources: 3
  require_step_citations_for:
    - "commands"
    - "parameters"
    - "security_sensitive"
lifecycle:
  link_check_freq: weekly
  gold_regression_freq: monthly
```

---

# 附录 F：Bot PR 描述模板（`agents/templates/pr/linux-bot.md`）

> 机器人创建 PR 时读此模板，替换 `{{...}}` 占位符。

````md
# linux-bot: {{pr_title}}

## Summary
- Domain: **linux**
- Generated: {{generated_count}}
- Updated: {{updated_count}}
- Deprecated/Removed: {{deprecated_count}}
- Batch ID: {{batch_id}}
- Run URL: {{run_url}}

## Topics included
| ID | Title | Risk | Level | Action | Notes |
|---|---|---:|---:|---:|---|
{{topics_table}}

## Sources (auto-collected)
- Total sources: {{sources_total}}

**Source types**
- man pages: {{sources_man}}
- official docs: {{sources_official}}
- distro docs: {{sources_distro}}
- other: {{sources_other}}

**Top domains**
{{top_domains}}

## Validator results
- Format / required sections: {{check_format}}
- Steps <= 12: {{check_steps_limit}} (violations: {{violations_steps}})
- Sources >= 3: {{check_sources_min}} (violations: {{violations_sources}})
- Key-step citations present: {{check_keystep_citations}}
- Link check: {{check_links}} (broken: {{broken_links_count}})
- Duplication check: {{check_duplicates}} (candidates: {{dup_candidates_count}})
- Safety keyword scan: {{check_safety_scan}} (flags: {{safety_flags_count}})

## Safety & risk notes
**High risk skills (require explicit reviewer attention)**
{{high_risk_list}}

**Medium risk skills**
{{medium_risk_list}}

**Low risk skills**
{{low_risk_list}}

> Rule of thumb (must hold for high-risk skills):
> - clear warning in `Safety & Risk`
> - safe preview step (dry-run / echo / show plan)
> - explicit confirmation requirement for irreversible actions
> - verification step present
> - troubleshooting pointer present

## Reviewer checklist (DoD)
- [ ] Each `skill.md` includes: Goal, When to use, When NOT to use, Prerequisites, Steps (<=12), Verification, Safety & Risk, Troubleshooting pointer, Sources (>=3)
- [ ] Key steps (commands/parameters) are traceable to Sources (step-level citations for critical steps)
- [ ] No prohibited content per `SAFETY.md`
- [ ] No large verbatim copy-paste from sources
- [ ] Link-check passes or broken links are removed/justified and not used as key evidence
- [ ] For high-risk skills: strong warnings + confirmation language present
- [ ] `metadata.yaml` includes at least: id, title, domain, level, risk_level, owners, last_verified

## How to reproduce locally
```bash
# Example (adjust to your tooling)
node agents/run_local.js --domain linux --topic "{{topic_id}}" --out skills
````

## Notes to reviewers

{{notes}}

```

---

# 附录 G：Linux 域首批 30 个主题种子清单（用于喂给 linux-bot）
> 目标：覆盖 filesystem/text/network/ssh/process/system/systemd/scheduling/packages/users/security 的常见核心任务，作为 v0.1-alpha 的内容骨架。

## filesystem（9）
1. `filesystem/find-files` — 用 find 精准查找文件与目录（按名称/时间/大小）— risk: **medium**  
2. `filesystem/locate-which-whereis` — locate/which/whereis/type 定位命令与路径 — risk: **low**  
3. `filesystem/safe-delete` — 安全删除：rm 的正确姿势与先预览后删除 — risk: **high**  
4. `filesystem/symlink-hardlink` — ln：符号链接 vs 硬链接 — risk: **low**  
5. `filesystem/permissions-chmod` — chmod 数字/符号写法与常见坑 — risk: **medium**  
6. `filesystem/ownership-chown` — chown/chgrp 递归修改与安全边界 — risk: **medium**  
7. `filesystem/acl-basics` — getfacl/setfacl 精细授权 — risk: **medium**  
8. `filesystem/disk-usage-du-df` — df/du 排查空间占用 — risk: **medium**  
9. `filesystem/archive-tar` — tar 打包解包（gzip/xz）最佳实践 — risk: **low**

## text（4）
10. `text/view-files-less-tail` — less/head/tail -f 看文件与日志 — risk: **low**  
11. `text/search-grep-ripgrep` — grep/rg 文本搜索与正则 — risk: **low**  
12. `text/replace-sed` — sed 批量替换、就地修改与备份策略 — risk: **medium**  
13. `text/parse-awk` — awk 提取列、统计、聚合 — risk: **low**

## network（4）
14. `network/download-curl-wget` — curl/wget（header、重试、代理）— risk: **low**  
15. `network/dns-dig-nslookup` — dig/nslookup 解析链路与 TTL — risk: **low**  
16. `network/connectivity-ping-traceroute` — ping/traceroute/tracepath 连通性诊断 — risk: **low**  
17. `network/ports-ss-lsof` — ss/lsof 找监听端口与进程 — risk: **medium**

## ssh（2）
18. `ssh/ssh-keys` — ssh-keygen + authorized_keys + ssh-agent — risk: **medium**  
19. `ssh/scp-rsync` — scp vs rsync（增量、断点、权限）— risk: **medium**

## process（3）
20. `process/ps-top-kill` — ps/top/kill（信号与优雅退出）— risk: **high**  
21. `process/background-nohup` — nohup、&、disown 与日志重定向 — risk: **medium**  
22. `process/tmux-session` — tmux 创建/分离/恢复会话 — risk: **low**

## system（2）
23. `system/system-info-uname-dmesg` — uname/lsb_release/dmesg 系统信息与启动排查 — risk: **low**  
24. `system/resources-free-vmstat` — free/vmstat/iostat 区分 CPU/内存/IO 瓶颈 — risk: **low**

## systemd（2）
25. `systemd/systemctl-service-status` — systemctl 状态/启动/重启/自启 — risk: **high**  
26. `systemd/journalctl-logs` — journalctl 按服务/时间/级别过滤 — risk: **low**

## scheduling（1）
27. `scheduling/cron-basics` — cron/crontab（环境差异与日志）— risk: **medium**

## packages（1）
28. `packages/package-manager-basics` — apt/dnf/pacman 安装/更新/回滚思路（参数化）— risk: **high**

## users（1）
29. `users/user-group-management` — useradd/usermod/groups/sudo 组 — risk: **high**

## security（1）
30. `security/sudoers-best-practice` — visudo/sudoers 最小授权与审计 — risk: **high**
```
