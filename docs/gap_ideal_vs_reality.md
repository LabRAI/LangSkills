# Ideal vs Reality Gap Report（放弃 Pages → 本地后端“联网检索”）

Date: 2026-01-17

> 目标：在“放弃 GitHub Pages，改为本机/局域网运行一个后端 HTTP 服务来分发与检索”前提下：
> 1) 完整测试后端是否可执行（含静态托管、安全边界、与 website/CLI/plugin 的兼容性）
> 2) 解析整个项目（入口/模块/数据流）
> 3) 把仓库里已写明的理想目标/门禁/里程碑与当前现实实现/证据逐条对照，列出全部差距（不省略）

## 0. 口径与范围（本报告的“完整性”定义）

### 0.1 “后端/联网检索”的定义
- 本报告里的“后端”= `scripts/serve-local.js` 启动的本地 HTTP 服务（`build-site` + `serve-site`），用于替代 GitHub Pages。
- “联网检索”= website/CLI/plugin 通过 HTTP 拉取同一份 `index.json`（以及按需拉取 `skills/**` markdown）完成检索与展示。
  - 备注：当前检索是在客户端过滤 `index.json`；没有服务端 query/search API。

### 0.2 本报告覆盖的“需求来源”（逐条对照的全集）
1) `docs/plan.md`（Q2–Q6 的目标与优先级）  
2) `README.md`：
   - `### 1.2 设计不变量（必须长期成立）`
   - `### 2.1 里程碑`：M0（9 条）、M1（4 条）、M2（3 条）
3) `docs/mohu.md`：所有 `## Missing` / `## Ambiguous` 条目（以 Acceptance 为准）
4) `docs/milestone_gap.md`：把“已跑通 vs 现实发布门禁”的差距作为补充需求来源（不与 README 冲突时并入）

> 超出上述文件的“理想需求”（例如“后端必须做公网 TLS/鉴权/多租户/服务端搜索 API”）一律记为 `Ambiguous`，不会假定为硬性需求。

## 1. 后端可执行性：完整测试（命令 + 输出 + 覆盖点）

Environment:
- CWD: `/Users/shatianming/Downloads/LangSkills`
- Node: `v23.11.0`

### 1.1 后端 automated smoke：`scripts/test-serve-local.js`（PASS）

Command:
```bash
node scripts/test-serve-local.js
```

Output:
```txt
OK: serve-local(build+serve) passed
- outDir: /var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-serve-local-bkO0jI
- baseUrl: http://127.0.0.1:52626/
- skills_count: 102051
OK: serve-local(--no-build) passed
- baseUrl: http://127.0.0.1:51480/
- skills_count: 102051
```

覆盖点（脚本断言）：
- `serve-local` 能 build+serve，也能 `--no-build` 仅 serve。
- `/index.json`：200 + JSON content-type + `Cache-Control: no-store` + schema/counts/长度一致性校验。
- 静态资源：`/`、`/app.js`、`/style.css`（content-type + no-store）。
- 内容拉取（atomic）：`skills/linux/filesystem/find-files/{library.md,skill.md,reference/sources.md}`。
- 内容拉取（template）：`skills/linux/m2-templates/parameterized-template/library.md` 包含 `{{id}}` 占位符。
- 安全边界（最小集）：目录不列出（`/skills/` → 404）；path traversal 变体不应返回 200。
- CLI online against backend：`cli/skill.js show linux/m2-param/p-000001` 的模板渲染生效（不再包含 `{{id}}`）。

### 1.2 全量本地回归入口：`scripts/self-check.js --m0 --m1 --m2 --skip-remote`（PASS）

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
OK   serve-site(local) - http://127.0.0.1:4323/index.json (skills_count=102051)
OK   cli(online) - search/show OK
OK   cli(online,m2) - parameterized template render OK
OK   cli - search/show OK
OK   cli(m2) - parameterized template render OK
OK   render-topics-table - wrote /var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-topics-AQmHeB/topics_table.md
OK   runner - state=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-runs-qepSDW/self-check-runner/state.json
OK   crawler - state=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/skill-crawl-runs-gCfBXt/self-check-crawl/crawl_state.json
OK   plugin(manifest) - host_permissions OK
OK   git-automation - dry-run + branch push OK
OK   create-pr(mock) - http://127.0.0.1:61915
OK   pages(remote) - skipped (--m1 offline default)
OK   m1(eval) - out=/var/folders/lr/81tyk63d4b51hg9bc73gd00r0000gn/T/eval-report-sewVCn/report.json (skills=2052)
OK   m1(lifecycle) - stale_gold=0
OK   m1(pr-score) - score=100
OK   m1(scale) - skills_count=2000
OK   m2(scale-index) - skills_count=100000 bytes=12571223
```

### 1.3 “全仓库可发布级别”合规门禁：`--fail-on-license-review-all`（PASS）

Command:
```bash
node scripts/validate-skills.js --strict --fail-on-license-review-all
```

Output:
```txt
OK: 2052 skills validated.
```

## 2. 项目解析（入口/数据流/模块）

完整结构与入口清单见：`docs/repo_inventory.md`。

后端/分发相关的关键链路（从数据到用户）：
1) `skills/`：技能数据源（atomic/template/parameterized 由 `skills/skillsets.json` 驱动扩展）
2) `scripts/build-site.js`：构建 `website/dist/`（`index.json` + 静态资源 + `skills/**` markdown 文件树）
3) `scripts/serve-site.js`：静态 HTTP 服务（路径逃逸保护 + 禁止目录访问 + `Cache-Control: no-store`）
4) `scripts/serve-local.js`：build+serve 一键入口（替代 Pages）
5) 消费端：
   - Website：`website/src/app.js` 同源拉取 `./index.json`，并按需拉取 `./skills/**` markdown；对 `template` 做 `{{...}}` 渲染
   - CLI：`cli/skill.js --base-url` 拉取 `index.json` 并过滤；按需拉取 markdown；对 `template` 做 `{{...}}` 渲染
   - Plugin：`plugin/chrome/popup.js` 从 `baseUrl` 拉取 `index.json` 并过滤；按需拉取 `skills/**/library.md`；对 `template` 做 `{{...}}` 渲染

## 3. 理想 vs 现实：逐条对照（不省略）

### 3.1 `docs/plan.md`（Q2–Q6）

1) Local-model support (Q2)  
- 理想：生成器提供 LLM Provider 抽象（至少 `ollama` + `mock`）并可在生成流程中调用。  
- 现实：✅ 已实现（`docs/mohu.md` Missing-001；`agents/llm/` + `agents/run_local.js`）。

2) Quality + License guard (Q3)  
- 理想：严格门禁 + 原文拷贝审计 + 来源/License 策略可审计。  
- 现实：✅ 已实现（`docs/mohu.md` Missing-002）且“灰名单清零”已达成（`docs/mohu.md` Missing-010，见 1.3）。

3) Long-running bots (Q4)  
- 理想：runner 队列/断点续跑/去重/速率控制。  
- 现实：✅ 已实现（`docs/mohu.md` Missing-003；`agents/runner/`）。

4) Auto git push (Q5)  
- 理想：默认 dry-run；失败回滚；本地自检覆盖关键路径。  
- 现实：✅ 本地关键路径已覆盖（`docs/mohu.md` Missing-004；`scripts/git-automation.js` + self-check）。  
- 差距（可选，对外证据链）：真实 GitHub PR 创建/权限策略/Release 线上闭环仍缺（Missing-013）。

5) Crawl scope + scaling (Q6)  
- 理想：per-domain seeds/allowlist/denylist；可扩展“发现→入队→生成→校验→去重→发布”。  
- 现实：⚠️ 框架具备，但多 domain 内容与来源覆盖仍不足（Missing-012）。

### 3.2 `README.md`：设计不变量（必须长期成立）

1) 每个 skill 一个文件夹，格式强制一致  
- 现实：✅ `scripts/validate-skills.js --strict` 强制。

2) `skill.md` 高度凝练，Steps <= 12  
- 现实：✅ `--strict` 校验 Steps<=12；但“凝练程度”属于内容质量，仍依赖治理/抽检。

3) 关键步骤必须可追溯（步骤级引用绑定）  
- 现实：✅ `--strict` 校验 citations；含命令 step 在严格模式下要求行尾 `[[n]]`。

4) 机器人只提 PR，不直推 main  
- 现实：⚠️ 代码/工作流按该策略设计；但真实 GitHub 线上闭环仍未验（Missing-013）。

5) 不可逆操作默认不自动执行  
- 现实：✅（技能格式强制 `Safety & Risk`；`SAFETY.md` 明确边界）。

6) 公信力来自可复现（gold/eval 可回归）  
- 现实：⚠️ 本地可复现（self-check 覆盖）；但“对外可访问的历史证据链”（Release 资产/线上报告）仍缺（Missing-013）。

### 3.3 `README.md`：M0（硬 DoD 9 条）

1) Repo 骨架齐全  
- 现实：✅ `self-check m0(repo-skeleton)` PASS。

2) Skill 标准 v1 定稿（含步骤-引用绑定）  
- 现实：✅ `validate-skills --strict` PASS。

3) Bot MVP：至少 1 个方向可自动生成 PR（端到端跑通）  
- 现实：⚠️ 本地已覆盖 git push + create-pr(mock) 关键路径；但未覆盖真实 GitHub PR（Missing-013）。

4) Validator MVP：可作为合并门禁  
- 现实：✅ CI/workflow 已跑 `--strict`（`.github/workflows/ci.yml`）。

5) Skills ≥ 50（20 silver、5 gold）  
- 现实：✅ 已远超（见 1.2）。

6) 官网 MVP：可搜索、可复制 library、显示等级与来源  
- 现实：✅ 已提供浏览器级 e2e：`npm run e2e`（Playwright；Missing-011 已验证）。  
  - 注：`self-check` 目前不默认跑浏览器，可按需把该命令纳入 CI/发布门禁。

7) CLI MVP：search/open/copy + 本地索引  
- 现实：✅ self-check 的 `cli`/`cli(online)` 覆盖。

8) 插件 MVP：检索/复制/跳转（不做自动执行）  
- 现实：✅ 已提供 plugin UI 的浏览器级 e2e：`npm run e2e`（Missing-011 已验证）。  
  - 注：该回归聚焦 popup UI（并 mock `chrome.*`），不等价于“真实加载扩展”的端到端。

9) 发布 v0.1-alpha（Demo GIF + Roadmap + 自动化徽章）  
- 现实：⚠️ 仓库内容/徽章/工作流具备；但“对外发布证明”（Release/tag 资产可访问、真实 PR 可见性）仍需线上闭环（Missing-013）。

### 3.4 `README.md`：M1（4 条）+ `docs/milestone_gap.md` 补充

1) Skills ≥ 2,000（silver/gold 占比上升）  
- 现实：✅ 满足（见 1.2）。

2) 固定周更节奏：每周 release + 变更日志 + eval 报告  
- 现实：⚠️ workflow/脚本具备，本地 eval 报告可生成；但“每周 Release 资产可访问”仍需要线上闭环（Missing-013）。

3) 社区治理稳定：PR 自动评分，低分 PR 不消耗 maintainer 时间  
- 现实：✅ `m1(pr-score)` PASS（见 1.2）。

4) 生命周期机制运行：link-check、stale、降级/归档流程有效  
- 现实：⚠️ 检测/门禁具备；但“自动降级/归档”策略与落地仍需明确 acceptance（见 `docs/milestone_gap.md` 对此的说明）。

### 3.5 `README.md`：M2（3 条）

1) 参数化/组合化/去重扩量  
- 现实：⚠️ 已实现 parameterized 生成 + 去重门禁 + 10 万级 index 回归（见 1.2）。  
- 差距（口径风险）：若你期望的是“真实多来源/多 topic 的 10 万”，需要先把口径写进 acceptance（见 4.3）。

2) 方向 bot 矩阵化（统一框架 + config 驱动）  
- 现实：⚠️ 框架存在（domain configs + orchestrator），但多数 domain 内容仍为空（Missing-012）。

3) Eval 与质量治理成为事实标准（可复用/对比）  
- 现实：⚠️ 本地可复现；但对外证据链（Release 留存/可比较基线/claim-evidence）仍缺（Missing-013 + 后续新增项）。

### 3.6 `docs/mohu.md`：现有 backlog（逐条列出，不省略）

已完成（`[x]`）：
- Missing-001 ~ Missing-011（见 `docs/mohu.md`）

未完成（`[ ]`）：
- Missing-012：多 domain 内容扩充
- Missing-013：线上真实 PR/Release 闭环（可选）

Ambiguous：
- Amb-001：integration 范围（见 `docs/mohu.md`）
- Amb-005：放弃 Pages 后，“本地后端联网检索”的范围与安全要求是什么？
- Amb-006：M2 “10 万级扩量”的口径与去重口径（真实 vs parameterized）

## 4. 全部差距清单（按“可执行缺口”列出）

> 说明：能直接落到 `docs/mohu.md` 的条目，用 mohu 的 Missing/Amb ID；否则以“新增建议”标注。

### 4.1 已确认仍缺（Mohu 中未完成的条目）
- Missing-012：多 domain 内容扩充（web/cloud/data/travel/devtools + integrations 多 topic）
- Missing-013：（可选）线上真实 PR/Release 闭环（即便放弃 Pages，也需要对外证据链时）

### 4.2 本地后端（serve-local）相对“更强后端”的差距（是否必须取决于你的口径）
- 新增建议（Ambiguous）：是否需要“服务端搜索 API”（避免每次拉 12MB+ 的 `index.json` 并在客户端过滤）？
- 新增建议（Ambiguous）：是否需要把 `serve-local` 升级为可公网使用（TLS/鉴权/多用户隔离/速率限制/日志审计）？
- 新增建议（Missing）：Chrome 插件若需要访问 LAN 地址（例如 `http://192.168.x.x:4173/`），需要扩展 `plugin/chrome/manifest.json` 的 `host_permissions`（当前只允许 `127.0.0.1/localhost`）。

### 4.3 口径/验收仍可能不一致的点（建议先澄清再实施）
- 新增建议（Ambiguous）：M2 “10 万级”是指：
  - A) `index.json` 中可检索条目 ≥ 100k（允许 parameterized 实例），还是
  - B) `skills/` 下真实内容文件夹 ≥ 100k，还是
  - C) 多 domain/多来源覆盖意义上的 100k（非模板堆叠）？
  需要先把口径写进 `docs/mohu.md` 的 acceptance，再谈“达成/未达成”。
