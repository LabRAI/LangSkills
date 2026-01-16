# Prompts

本仓库偏向“可执行的 playbook”，生成与提质时建议使用以下最小提示词（可供 bot/人工复用）。

## 生成 skill 初稿（最小）

- 目标：生成 `skill.md` + `library.md` + `metadata.yaml` + `reference/sources.md`
- 约束：Steps<=12；Sources>=3；必须包含 Verification + Safety & Risk；高风险必须有 dry-run 与明确确认

## 提质（从 bronze → silver）

- 补充来源（优先 man / 官方文档 / 发行版文档）
- 增加失败排查入口（写入 `reference/troubleshooting.md`）
- 增加可复现的 Verification（可复制运行）

