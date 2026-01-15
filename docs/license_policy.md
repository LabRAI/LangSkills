# License Policy（白/灰/黑）

本仓库把每条来源的许可信息当作“可审计字段”，并用 `scripts/license-policy.json` 定义可执行规则；校验入口是 `node scripts/validate-skills.js --strict`。

## 1) 要求（写在哪里）

每个 skill 的 `skills/**/reference/sources.md` 必须对每条来源写 `License:`，例如：

```md
## [1]
- URL: https://example.com/doc
- Accessed: 2026-01-15
- Summary: ...
- Supports: Steps 1-3
- License: CC-BY-4.0
```

## 2) 三类策略（白/灰/黑）

规则文件：`scripts/license-policy.json`

- **allowed（白名单）**：允许作为来源使用（仍要求“不要大段原文拷贝”，并在 Steps 里做 `[[n]]` 绑定）。
- **review（灰名单）**：允许进入仓库（通常是 bronze），但需要人工补齐/确认；升级到 silver/gold 前应清零灰名单来源。
- **denied（黑名单）**：禁止作为来源；一旦出现会被 `validate-skills --strict` 直接阻断（CI 失败）。

## 3) 校验命令（可执行）

```bash
# 默认：黑名单阻断；灰名单警告（不失败）
node scripts/validate-skills.js --strict

# 严格：灰名单也当失败（用于 silver/gold 升级或发布门禁）
node scripts/validate-skills.js --strict --fail-on-license-review
```

## 4) License 字段的写法（示例）

推荐写法：优先填 SPDX（或常见的规范写法）；不确定就用灰名单 token（例如 `unknown`）并在 review 时补齐。

- OK（白名单示例）：`MIT` / `Apache-2.0` / `CC-BY-4.0` / `CC0-1.0`
- 需要复核（灰名单示例）：`unknown` / `custom` / `unlisted`
- 阻断（黑名单示例）：`proprietary` / `source-available` / `CC-BY-NC-4.0` / `CC-BY-ND-4.0`

## 5) 与“避免侵权”的关系

License 字段只解决“来源可追溯与可阻断”；是否侵权还取决于内容使用方式。

本仓库的额外硬门禁：

- 不允许大段原文拷贝：`node scripts/validate-skills.js --strict --require-no-verbatim-copy --cache-dir .cache/web`
- Steps 必须做来源绑定：`[[n]]`（每条来源在 `reference/sources.md` 里有对应 `## [n]` 块）

