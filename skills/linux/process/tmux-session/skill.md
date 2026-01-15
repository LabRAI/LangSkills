# 会话保持：tmux（创建/分离/恢复）

## Goal
- 用 `tmux` 创建可断线重连的终端会话：断开 SSH 后任务继续跑，回来再 attach。

## When to use
- 需要在远端跑长任务/多窗口操作，但不想担心断线
- 需要多个 pane 并行看日志/运行命令
- 需要保留滚动缓冲并在里面搜索

## When NOT to use
- 你需要系统级托管/自启动（优先 systemd）
- 你无法安装 tmux 或政策不允许（可退而用 screen/nohup）

## Prerequisites
- Environment: Linux shell + tmux installed
- Permissions: 无（本地会话）
- Tools: `tmux`
- Inputs needed: 会话名（可选）+ 你要跑的命令/任务

## Steps (<= 12)
1. 新建会话：`tmux new -s <name>`（进入后开始执行你的命令）[[1][2][3]]
2. 分离会话：按 `Ctrl-b d`（detach）[[1][2]]
3. 列出会话：`tmux ls`[[1][2][3]]
4. 重新连接：`tmux attach -t <name>`[[1][2][3]]
5. 常用操作：`Ctrl-b c` 新窗口，`Ctrl-b %` 垂直分屏，`Ctrl-b "` 水平分屏[[1][2]]

## Verification
- detach 后 `tmux ls` 仍能看到会话
- 重连后原窗口/任务仍在运行

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（会话管理）
- Privacy/credential handling: tmux 会话中可能包含敏感输出；共享屏幕/录制前脱敏
- Confirmation requirement: 退出 tmux 前确认任务状态；必要时在会话中记录日志文件位置

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: tmux(1): https://man.archlinux.org/man/tmux.1.en.txt
- [2] tmux wiki: Getting Started: https://github.com/tmux/tmux/wiki/Getting-Started
- [3] Debian man: tmux(1): https://manpages.debian.org/bookworm/tmux/tmux.1.en.html
