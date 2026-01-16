# Skill Format（v1）

每个 `skill.md` 必须包含以下章节（缺一不可）：

1. Goal
2. When to use / When NOT to use
3. Prerequisites
4. Steps（<= 12）
5. Verification
6. Safety & Risk
7. Troubleshooting（指向 `reference/`）
8. Sources（>= 3）

## 步骤-引用绑定

关键步骤（命令、参数、关键决策）建议在步骤行尾标注来源编号，例如：

`[[1]]`（多来源可写 `[[1][2]]`）

## `metadata.yaml`

至少包含：

- `id`：`<domain>/<topic>/<slug>`
- `title`：人类可读标题
- `domain` / `level` / `risk_level`
- `owners` / `last_verified`（silver/gold）
