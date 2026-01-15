# 进程管理：ps/top/kill（含信号与优雅退出）

## Goal
- 用 `ps/top` 找到目标进程与资源瓶颈，用 `kill` 按“先温和后强制”的顺序安全终止进程。

## When to use
- 进程卡死/占用 CPU 或内存异常，需要定位并处理
- 服务异常需要确认是否有多个实例/僵尸进程
- 脚本启动了错误的后台任务需要停止

## When NOT to use
- 你不确定 PID 属于哪个服务且可能影响生产（先确认 owner/用途）
- systemd 管理的服务（优先 `systemctl stop` 而不是直接 kill）

## Prerequisites
- Environment: Linux shell
- Permissions: 终止其他用户进程通常需要 sudo/root
- Tools: `ps` / `top` / `kill`
- Inputs needed: 进程名或 PID（以及你期望的行为：优雅退出/强制终止）

## Steps (<= 12)
1. 列出进程（抽样定位）：`ps aux | head` 或 `ps -ef | head`[[1]]
2. 按需格式化输出：例如 `ps -eo pid,ppid,user,%cpu,%mem,etime,cmd | head`[[1]]
3. 实时观察资源：`top`（在 top 内按 `P/M` 排序，看 %CPU/%MEM）[[2]]
4. 先优雅终止：`kill -TERM <pid>`（给进程时间清理资源）[[3][4]]
5. 仍不退出再强制：等待几秒后 `kill -KILL <pid>`（最后手段）[[3][4]]

## Verification
- `ps`/`top` 中进程不再存在（或资源恢复正常）
- 如是服务进程：检查服务是否被自动拉起（systemd/supervisor）并做相应处理

## Safety & Risk
- Risk level: **high**
- Irreversible actions: kill 可能导致未保存数据丢失、服务中断；`-KILL` 无法让进程清理资源
- Privacy/credential handling: ps/top 输出可能包含命令行参数（token/密码）；分享前脱敏
- Confirmation requirement: 终止前确认 PID 对应服务与影响范围；优先使用服务管理器停服务；严格遵循先 TERM 后 KILL

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: ps(1): https://man.archlinux.org/man/ps.1.en.txt
- [2] Arch man: top(1): https://man.archlinux.org/man/top.1.en.txt
- [3] POSIX kill specification: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/kill.html
- [4] Arch man: kill(1): https://man.archlinux.org/man/kill.1.en.txt
