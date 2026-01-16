# Governance

## DoD（Definition of Done）

- 格式完整：见 `docs/skill-format.md`
- Sources>=3；关键步骤可追溯
- 来源策略：来源域名需符合 `agents/configs/<domain>.yaml` 的 `source_policy`（allow/deny domains）
- `reference/sources.md` 需包含 `License:` 字段，并遵循 `scripts/license-policy.json`（白/灰/黑）
  - `denied`（黑名单）会阻断合并（例如 `proprietary`/`source-available`/`CC-BY-NC-*`）
  - `review`（灰名单，如 `unknown`）会输出警告；需要人工补齐后才能把技能升级为 silver/gold
- 链接可达（失效需替换/降级/移除关键依赖）
- 不包含大段原文拷贝（可用抓取缓存做门禁：`node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir <cache>`）
- 重复治理：避免复制粘贴；`--strict` 会做 `library.md` 的重复检测（完全一致会失败）
- 风险一致性：`--strict` 会做关键风险命令扫描，要求 `metadata.yaml risk_level` 不低报（例如 `rm -rf`/`mkfs`/`dd if=` 等）
- 等级治理：silver/gold 需要 `owners` + `last_verified`（并且 `last_verified` 为 `YYYY-MM-DD`）

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

# 将 silver/gold 的灰名单 License 当作失败（用于升级门禁）
node scripts/validate-skills.js --strict --fail-on-license-review

# 全仓库灰名单 License 当作失败（用于发布门禁）
node scripts/validate-skills.js --strict --fail-on-license-review-all
```
