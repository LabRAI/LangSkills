# Contributing

本仓库的目标是“可复现、可验证、可治理”的 skills，而不是教程堆积。

## 基本要求（DoD）

- 每个 `skill.md` 必须包含：Goal / When to use / When NOT to use / Prerequisites / Steps(<=12) / Verification / Safety & Risk / Troubleshooting pointer / Sources(>=3)
- 关键步骤（命令、参数、关键决策）需要能追溯到来源（建议在步骤行尾标注 `[[n]]`）
- 不要粘贴大段原文（避免侵权）；更倾向“摘要 + 指向链接 + 访问日期”
- 高风险操作（删除/权限/支付/提交）必须包含：强提示 + 安全预演（dry-run/echo/plan）+ 明确确认语言

## 提交 PR 前自检

- [ ] 我提供了至少 3 条公开来源（man/官方文档/发行版文档等）
- [ ] 我没有复制付费/不可转载内容
- [ ] 我补齐了 Verification 与 Safety & Risk
- [ ] 若涉及不可逆操作，我加入了强提示与确认步骤

## 文件与命名

- 目录：`skills/<domain>/<topic>/<slug>/`
- `metadata.yaml` 的 `id` 必须与目录一致：`<domain>/<topic>/<slug>`
