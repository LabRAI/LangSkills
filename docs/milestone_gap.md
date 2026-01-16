# Milestone Gap Report（M0/M1/M2）

> 目标：把“自检已跑通的结果”与 README 里程碑（M0/M1/M2）+ docs/plan.md 的现实需求之间的差距，整理成可追踪清单。

## Snapshot（2026-01-16）

**已跑通（本地可复现）**
- `node scripts/self-check.js --m0 --m1 --m2 --skip-remote`：PASS（见 `docs/verify_log.md`）
- 仓库 skills 规模：`website/dist/index.json` 统计为 `total=50 (bronze=25, silver=20, gold=5)`
- 严格门禁：`node scripts/validate-skills.js --strict`：PASS（仍有 bronze 的 `License: unknown` 警告）
- Silver/Gold license 门禁：`node scripts/validate-skills.js --strict --fail-on-license-review`：PASS

**仍未满足（按“现实发布门禁”理解）**
- 全仓库清零灰名单：`node scripts/validate-skills.js --strict --fail-on-license-review-all`：FAIL（bronze 仍有 `unknown`）
- Tier0 must-ingest（上游 github_repo）仍缺 ingest 闭环：见 `docs/mohu.md` 的 `Missing-007`

---

## M0（README “硬 DoD”）对照

> 参考：`README.md` 的 “#### M0（2 天内，必须达成）”

1) Repo 骨架（README/LICENSE/docs/workflows/安全边界）  
✅ 已满足：`scripts/self-check.js --m0` 的 `m0(repo-skeleton)` 覆盖必需文件/工作流存在性。

2) Skill 标准 v1（结构 + Steps<=12 + Sources>=3 + 引用绑定）  
✅ 已满足：`scripts/validate-skills.js --strict` 对 headings/steps/citations/sources 进行硬校验；规范见 `docs/skill-format.md`、`docs/governance.md`。

3) Bot MVP：至少 1 个方向可“自动生成 PR”（端到端）  
⚠️ 代码/工作流已具备，但需要线上真实验证：
- 已具备：`.github/workflows/agent-generate.yml`（生成 skills → validate → push 分支 → create PR）
- 本地仅回归了关键子路径：`git-automation`（临时 repo 推分支）+ `create-pr(mock)`（mock server），不等价于真实 GitHub PR。

4) Validator MVP：可作为合并门禁  
✅ 已满足：CI 使用 `node scripts/validate-skills.js --strict`；`pr-score` workflow 对 PR 做硬门禁。

5) Skills ≥ 50：至少 20 silver、5 gold  
✅ 已满足（当前仓库）：`total=50, silver=20, gold=5`（见上方 snapshot）。
⚠️ 自检门槛与 README 口径略不同：`self-check` 目前只断言 `silver+gold>=20`，但实际数据满足 README 的更严格口径。

6) 官网 MVP：可搜索、可复制 library、显示等级与来源  
✅ 已覆盖“生成与索引链路”：`build-site` + `serve-site(local)` 产出 `website/dist/` 并可被 CLI 使用。  
⚠️ 未覆盖 UI/交互的浏览器级 e2e（目前 self-check 不跑浏览器）。

7) CLI MVP：search/open/copy + 本地索引  
✅ 已满足：`scripts/self-check.js` 的 `cli`/`cli(online)` 覆盖 search/show 基本路径。

8) 插件 MVP：检索/复制/跳转（不做自动执行）  
⚠️ 仅做了 manifest 与 host_permissions 回归（`plugin(manifest)`）；插件功能本身未做 e2e/集成回归。

9) 发布 v0.1-alpha：Demo GIF + Roadmap + 自动化徽章（CI/link-check/site build）  
⚠️ 资产/工作流已具备（demo.gif、CI/link-check/build-site），但“release/tag + 对外可访问的报告/站点”仍依赖真实 GitHub Pages/Release 运行结果。

---

## M1（README）对照

> 参考：`README.md` 的 “#### M1（1-2 个周，确保‘最坏也留痕’）”

1) Skills ≥ 2,000（silver/gold 占比上升）  
❌ 未满足（现实数据）：仓库当前 skills=50。  
⚠️ 仅具备“规模回归能力”：`scripts/self-check.js --m1` 会生成 2,000 条 synthetic skills 并验证 validate/build-site 可跑通，但不代表真实技能库已扩容。

2) 固定周更节奏：每周 release + 变更日志 + eval 报告  
⚠️ 部分具备：
- 已有每周定时：`.github/workflows/eval.yml`、`.github/workflows/lifecycle.yml`（cron weekly）
- 但产物目前主要是 Actions artifact；未形成“release 产物/对外可访问的历史报告”（例如 commit 到 `eval/reports/` 或挂到 Release）。

3) 社区治理稳定：PR 自动评分，低分 PR 不消耗 maintainer 时间  
✅ 已具备：`.github/workflows/pr-score.yml` 对 PR 做硬门禁；`scripts/pr-score.js` 可生成报告。

4) 生命周期机制运行：link-check、stale、降级/归档流程有效  
⚠️ 部分具备：
- 已有每周定时 lifecycle（stale_gold gate）：`.github/workflows/lifecycle.yml`
- 已有 link-check 工作流：`.github/workflows/link-check.yml`
- “降级/归档流程”更偏治理流程，目前更像“检测+报告+门禁”，而不是自动执行降级/归档（需明确策略与落地方式）。

---

## M2（README）对照

> 参考：`README.md` 的 “#### M2（1 个月，冲 10 万级）”

1) 依靠参数化/组合化/去重扩量，而不是堆重复文档  
⚠️ 部分具备（门禁侧）：
- `validate-skills --strict` 有“重复检测”（library 完全一致会失败）
❌ 但缺少“系统化的参数化/组合化生成闭环”（数据结构、生成策略、覆盖统计与验收口径）。

2) 方向 bot 矩阵化（统一框架 + config 驱动）  
⚠️ 基础具备（domain/config/runner/orchestrator），但矩阵规模不足：
- 当前默认 domains：`linux`/`productivity`/`integrations`
- 未形成“多 domain、多 source、多策略”的可配置实验矩阵与覆盖统计。

3) Eval 与质量治理成为事实标准（可被他人复用/对比）  
⚠️ 已有 eval harness + 周期性运行，但仍缺：
- 面向 release 的“可访问历史报告/对比基线”
- 与 claims 的系统映射（若要对外宣称，需要证据链）

4) 10 万级工程回归  
✅ 已具备“索引生成的规模回归能力”：`scripts/self-check.js --m2` 会生成 100k synthetic index（metadata-only）并验证 build-site 输出体积与 schema 约束。  
❌ 但不代表真实 skills 数据已达到 100k。

---

## 当前最关键的现实缺口（优先级建议）

1) `Missing-007`（Tier0 github_repo ingest）  
- 这是把 must-ingest 上游 repo 变成“可跑、可增量、可审计”闭环的关键缺口，直接影响 M1/M2 的扩量与证据链。

2) M1 的“真实周更产物化”  
- 从“Actions artifact”升级到“release/Pages 可访问的历史报告 + changelog 对齐”。

3) M1/M2 的“真实数据扩量”口径与验收  
- 明确：什么算 2k/100k（原子/组合/参数化）、去重口径、覆盖统计与质量门禁。

