# 后台任务：nohup、&、disown 与日志重定向

## Goal
- 把长任务放到后台并在断开 SSH 后仍持续运行：用 `nohup` + 重定向 + `&`，必要时用 `disown`。

## When to use
- 需要跑一个耗时命令（下载/训练/备份）但不想一直占用终端
- SSH 连接不稳定，担心断线导致任务终止

## When NOT to use
- 任务需要可观测/可管理（优先 systemd/tmux/队列系统）
- 你不确定任务是否会无限输出日志或占满磁盘（先设置日志策略）

## Prerequisites
- Environment: Linux shell (bash/zsh)
- Permissions: 执行命令权限 + 写日志文件权限
- Tools: `nohup`（可选）+ shell job control（`jobs`/`disown`）
- Inputs needed: 要运行的命令 + 输出日志路径

## Steps (<= 12)
1. 直接后台运行并记录日志：`nohup <cmd> >out.log 2>&1 &`（注意把 stdout/stderr 都落盘）[[1]]
2. 确认作业与 PID：`jobs -l`（或记录 `$!`）[[2][3]]
3. 可选：从 shell 作业表移除并避免 SIGHUP：`disown -h %<job>`[[2][3]]
4. 验证：`tail -n 50 out.log` 看任务是否持续输出；必要时通过 PID 确认仍在运行[[1]]

## Verification
- 断开并重连 SSH 后，任务仍在运行且日志持续增长
- 任务完成后退出码/产物符合预期

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 后台任务可能持续占用 CPU/内存/磁盘；错误脚本可能造成数据破坏
- Privacy/credential handling: 日志可能包含敏感数据；限制日志权限并避免上传/公开
- Confirmation requirement: 为后台任务设置明确输出文件与停止方式；生产环境优先用可管理的服务/作业系统

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: nohup(1): https://man.archlinux.org/man/nohup.1.en.txt
- [2] GNU Bash manual: Job Control Builtins: https://www.gnu.org/software/bash/manual/html_node/Job-Control-Builtins.html
- [3] Arch man: bash(1): https://man.archlinux.org/man/bash.1.en.txt
