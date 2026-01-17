# 结束进程：pkill/killall/kill 的安全信号策略（TERM→KILL）

## Goal
- 用信号（TERM→KILL）安全结束目标进程，避免误杀，并在必要时收集信息以便排查。

## When to use
- 某个进程卡死/占用资源，需要优雅终止再强制终止
- 需要按进程名批量结束（谨慎）

## When NOT to use
- 不确定匹配规则会命中哪些进程（先用 pgrep/ps 预览）
- 生产环境关键服务（先走维护窗口与回滚）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常只能终止自己拥有的进程；系统服务可能需要 sudo
- Tools: `pgrep`/`pkill`, `kill`, `killall`
- Inputs needed: 目标进程名或 PID，以及期望的终止方式（优雅/强制）

## Steps (<= 12)
1. 先确认会命中哪些进程：`pgrep -a '<pattern>'`（只列出，不终止）[[2]]
2. 如需按名称终止，优先用 pkill 且先 TERM：`pkill -TERM -f '<pattern>'`[[2]]
3. 按 PID 终止：`kill -TERM <pid>`（优雅退出）[[1]]
4. 等待片刻后检查是否仍存在：`pgrep -a '<pattern>'` 或 `ps -p <pid>`[[2]]
5. 仍不退出再升级为 KILL：`kill -KILL <pid>` 或 `pkill -KILL -f '<pattern>'`（最后手段）[[1][2]]
6. 谨慎使用 killall：确认进程名唯一，再执行 `killall -TERM <name>`[[3]]

## Verification
- 目标 PID/进程名不再出现在 `ps`/`pgrep` 输出中
- 服务需要重启时，确认恢复策略（systemd/容器/脚本）

## Safety & Risk
- Risk level: **high**
- Irreversible actions: KILL 会强制终止，可能导致数据丢失/状态损坏；误杀可能影响系统/服务
- Privacy/credential handling: 排查日志可能包含用户数据；共享前脱敏
- Confirmation requirement: 始终先 pgrep/ps 预览；优先 TERM；KILL 只作为最后手段

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: kill(1): https://man.archlinux.org/man/kill.1.en.txt
- [2] Arch man: pkill(1): https://man.archlinux.org/man/pkill.1.en.txt
- [3] Arch man: killall(1): https://man.archlinux.org/man/killall.1.en.txt
