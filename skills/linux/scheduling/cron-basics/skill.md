# 定时任务：cron/crontab（环境差异与日志）

## Goal
- 用 `crontab` 安全地配置定时任务：理解最小环境差异、用绝对路径、记录日志，并验证任务确实在跑。

## When to use
- 周期性任务（备份、清理、同步、健康检查）
- 临时自动化但不想引入更重的调度系统

## When NOT to use
- 需要依赖复杂环境/密钥管理/失败重试（优先 systemd timers/队列系统）
- 任务有高风险写操作且没有回滚/审计策略

## Prerequisites
- Environment: Linux with cron daemon
- Permissions: 编辑自己 crontab；系统级任务需要 sudo/root
- Tools: `crontab`
- Inputs needed: 任务命令（建议可重入）+ 计划时间 + 日志输出位置

## Steps (<= 12)
1. 编辑/查看：`crontab -e` 写入任务；用 `crontab -l` 确认生效[[1]]
2. 写任务时用绝对路径，并明确 shell/环境：必要时在 crontab 顶部设置 `SHELL=/bin/bash`、`PATH=...`[[2][3]]
3. 先手动跑命令确认无误，再写入计划表达式：`*/5 * * * * /usr/local/bin/job ...`[[2]]
4. 记录日志并避免无上限增长：`... >>/var/log/job.log 2>&1`（配合 logrotate）[[2][3]]
5. 验证：等待一个周期后用 `crontab -l` + 查看日志确认任务确实执行[[1]]

## Verification
- 日志中出现周期性执行记录，且退出码/产物符合预期
- 任务在重启后仍按计划执行（如需要）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: cron 会自动反复执行；错误任务可能造成持续破坏（删文件、占满磁盘、刷爆接口）
- Privacy/credential handling: 日志可能包含敏感参数；避免把 secret 写进 crontab（用受控配置/环境）
- Confirmation requirement: 上线前先在测试机/小范围验证；高风险任务加入锁/幂等保护并保留回滚方案

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: crontab(1): https://man.archlinux.org/man/crontab.1.en.txt
- [2] Arch man: crontab(5): https://man.archlinux.org/man/crontab.5.en.txt
- [3] Arch man: crond(8): https://man.archlinux.org/man/crond.8.en.txt
