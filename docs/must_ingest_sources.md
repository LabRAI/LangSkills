# Must-Ingest Sources（M0 起步清单）

这份清单定义“至少吃掉的库/站点”到底是哪一些，并把它们落实为 `agents/configs/sources.yaml` 里的 **stable IDs**（用于长期跑 bot、统计覆盖率、以及后续扩展）。

## A. Tier0（会议提到的上游 skills/spec repo，reference-only）

这些来源的用途是：作为 **对照/证据/映射**（reference-only），不直接复制全文进本仓库。

| Source ID | Type | Upstream | 主要包含 | 本仓库策略 |
|---|---|---|---|---|
| `upstream_anthropic_skills` | `github_repo` | `anthropics/skills` | `skills/**/SKILL.md` + `spec/` + `template/` | per-file/per-skill license 记录；遇到 `source-available` 必须阻断 |
| `upstream_agentskills_spec` | `github_repo` | `agentskills/agentskills` | spec/SDK/validator | 作为标准基准线，指导兼容与校验规则 |
| `upstream_context_engineering_skills` | `github_repo` | `muratcankoylan/Agent-Skills-for-Context-Engineering` | `skills/**/SKILL.md` | reference-only（提炼/映射），不逐字搬运 |
| `upstream_claude_scientific_skills` | `github_repo` | `K-Dense-AI/claude-scientific-skills` | `scientific-skills/**/SKILL.md` | reference-only（提炼/映射），不逐字搬运 |

对应配置：`agents/configs/sources.yaml`

## B. Tier1（长期运行的稳定公开来源，primary）

这些来源的用途是：作为 bot “长期主粮”，支持按 `refresh.interval` 周期性增量抓取并持续产出候选。

| Source ID | Domain | Seeds（示例） | 刷新 |
|---|---|---|---|
| `linux_tier1_web` | `linux` | `man7.org` / GNU 手册 / Arch Wiki / POSIX | `ttl: 7d` |
| `productivity_tier1_web` | `productivity` | ICMJE / NSF / NIH / Purdue OWL | `ttl: 14d` |
| `integrations_slack_docs` | `integrations` | `https://api.slack.com/` | `ttl: 7d` |

对应配置：`agents/configs/sources.yaml`

## C. 合规与边界（明确写死，不“隐式扩大”）

- 只抓取 **公开可访问** 的来源；不做登录态爬取；不做 JS 渲染站点（目前 crawler 只做 HTML `href=` 发现）。
- 抓取范围必须在 allowlist 内：`agents/configs/<domain>.yaml` 的 `source_policy.allow_domains/deny_domains` 会被 crawler 强制执行并写入 `runs/<run-id>/crawl_log.jsonl`。
- 每条来源必须写 `License:`，并遵循 `scripts/license-policy.json`（白/灰/黑）；黑名单直接阻断（见 `docs/license_policy.md`）。

## D. 还缺的一步（工程任务）

当前 orchestrator/crawler/extractor 的长跑闭环主要覆盖 `http_seed_crawl`（docs 站点）；Tier0 的 `github_repo` 仍需要补齐“远端拉取/增量/解析”能力，才能做到真正意义上的“吃掉上游 repo 全量内容”。

建议以一个独立 Missing 项跟踪实现（见 `docs/mohu.md`）。

