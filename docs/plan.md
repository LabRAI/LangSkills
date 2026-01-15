# Plan

本计划聚焦修复会议问题 **2–6**（按优先级：2 → 3 → 4 → 5 → 6），把“技能内容库 + 生成/校验/分发”补齐为可长期运行、可审计、可安全自动化推进的体系。

## Goals

- 支持 **网页端集成（integration）** 的技能生产与分发（至少具备可扩展的 domain/config/来源策略与抓取管道）。
- 支持 **本地开源模型**（例如 Ollama）参与生成/提质流程（不依赖外部服务即可跑通一条生成链路）。
- 机器人生成的 markdown **可审计**（来源、抓取证据、关键步骤引用绑定、避免大段原文拷贝）。
- 支持部署 **可连续运行数天到数星期** 的机器人：具备稳定数据源、队列/断点续跑、去重与迭代策略。
- 自动化 git push/PR 流程可控且可回滚（默认安全、支持 dry-run、明确权限边界）。

## Requirements (Prioritized)

1. **Local-model support (Q2)**: 生成器提供 LLM Provider 抽象，至少支持：
   - `ollama`（本地开源模型）
   - `mock`（离线可复现测试）
   并能在生成流程中调用（例如 rewrite/提质阶段）。
2. **Quality + License guard (Q3)**: 在现有 `validate-skills --strict` 基础上补齐：
   - “大段原文拷贝”检测（基于抓取缓存与指纹）
   - 来源与 license 风险记录策略（可配置/可审计）
3. **Long-running bots (Q4)**: 新增可持久化的 runner（队列、进度、断点续跑、速率控制、去重），能持续迭代并覆盖既定 sources。
4. **Auto git push (Q5)**: 新增安全的自动提交/推送（或 PR 创建）脚本：
   - 默认 dry-run
   - 明确分支策略与失败回滚
   - 可在本地自检脚本中覆盖关键路径
5. **Crawl scope + scaling (Q6)**: 明确机器人抓取范围：
   - per-domain seeds/allowlist/denylist
   - 可扩展的“发现→入队→生成→校验→去重→发布”流程

## Baseline Commands

```bash
# Current baseline health check (no network required if --skip-remote)
node scripts/self-check.js --skip-remote

# Strict gate on repo skills/
node scripts/validate-skills.js --strict
```

