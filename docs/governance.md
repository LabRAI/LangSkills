# Governance

## DoD（Definition of Done）

- 格式完整：见 `docs/skill-format.md`
- Sources>=3；关键步骤可追溯
- 来源策略：来源域名需符合 `agents/configs/<domain>.yaml` 的 `source_policy`（allow/deny domains）
- `reference/sources.md` 需包含 `License:` 字段（未知可写 `unknown`，但需要可审计）
- 链接可达（失效需替换/降级/移除关键依赖）
- 不包含大段原文拷贝（可用抓取缓存做门禁：`node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir <cache>`）
- 重复治理：同义技能用 alias/redirect，不要复制粘贴

## 方向治理（domain）

每个 domain 固化两份文件：

- `docs/domains/<domain>.md`：范围定义、来源策略、禁止事项
- `agents/configs/<domain>.yaml`：bot 配置（主题列表/白名单/风险词等）

## 推荐门禁命令

```bash
# 严格门禁（结构/引用/抓取证据/无 TODO/安全字段 + license 字段 + source_policy）
node scripts/validate-skills.js --strict

# 原文拷贝审计（需要抓取缓存；默认 cache 在 .cache/web）
node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web
```
