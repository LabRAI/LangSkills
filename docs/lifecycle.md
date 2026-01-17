# Lifecycle（stale/archived）

本仓库把 “技能内容” 当作可长期运营的数据资产，因此需要一个可自动化的生命周期机制：

- **fresh**：近期验证过（`metadata.yaml:last_verified` 在阈值内）
- **stale**：需要复核/回归（例如 silver/gold 长期未验证）
- **archived**：长期无人维护或已不再推荐（保留历史但不推荐使用）

当前生命周期状态的主要输入来自每条 skill 的 `metadata.yaml`：

- `level`: `bronze|silver|gold`
- `last_verified`: `YYYY-MM-DD`（gold/silver 建议必须有）
- `tags`: 可包含 `stale`、`archived`

## 脚本：`scripts/lifecycle.js`

脚本会扫描 `skills/**/metadata.yaml` 并输出一份 JSON 报告（以及可选的自动修正）。

常用命令：

```bash
# 生成报告（不改文件）
node scripts/lifecycle.js --out runs/lifecycle/local/report.json

# 对 stale 的 silver/gold 进行降级建议（并写回 metadata.yaml）
node scripts/lifecycle.js --out runs/lifecycle/local/report.json --downgrade --apply

# 仅作为门禁：发现 stale gold 则失败（用于 CI/定时任务）
node scripts/lifecycle.js --out runs/lifecycle/local/report.json --fail-on-stale-gold
```

关键参数：

- `--stale-days N`：默认 90 天；超过则标记 stale（仅 silver/gold）
- `--archive-days N`：默认 365 天；超过则标记 archived（仅 silver/gold）
- `--downgrade`：对 stale 的等级给出降级（gold→silver，silver→bronze）
- `--apply`：把 `stale/archived` tag 与降级写回 `metadata.yaml`
- `--fail-on-stale-gold`：若存在 stale gold，返回非 0（用于门禁）

## GitHub Actions：`.github/workflows/lifecycle.yml`

定时任务每周运行一次：

- 生成 `runs/lifecycle/<run_id>/report.json`
- 作为 artifact 上传
- 若 `--fail-on-stale-gold` 失败则 Gate 阶段失败（阻断）

如果你希望把 lifecycle 的 `--apply/--downgrade` 结果自动变成 PR，可以结合：

- `scripts/git-automation.js`（创建分支、提交并 push）
- `scripts/create-pr.js`（创建 PR）

仓库已提供一个手动触发的 workflow：`.github/workflows/lifecycle-apply.yml`（dry-run 默认开启；关闭后会把变更提交到 `bot/lifecycle/<run_id>` 分支并自动创建 PR）。
