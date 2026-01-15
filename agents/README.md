# Agents

这里放置自动化相关组件（generator/validator/curator）、各 domain 的配置，以及 PR 模板等。

- `agents/configs/`：每个 domain 的 bot 配置（主题列表、来源白名单、风险词等）
- `agents/configs/sources.yaml`：sources registry（Tier1 官方文档 + Tier0 上游技能库；配置即接入）
- `agents/run_local.js`：本地生成器（从 configs 生成 skills 骨架）
- `agents/crawler/`：按 domain `seeds` + `source_policy` 做来源发现/入队（状态写入 `runs/<run-id>/crawl_state.json`；抓取缓存写入 `.cache/web/`）
- `agents/extractor/`：把 crawler 的 raw snapshot 转成 `TopicCandidates`（断点续跑），写入 `runs/<run-id>/candidates.jsonl`
- `agents/runner/`：长跑 runner（队列/断点续跑/循环），写入 `runs/<run-id>/state.json`
- `agents/orchestrator/`：scheduler（组合 crawler/runner 并输出覆盖率/吞吐指标），用于 days/weeks 长跑
- `agents/templates/pr/`：机器人 PR 描述模板
