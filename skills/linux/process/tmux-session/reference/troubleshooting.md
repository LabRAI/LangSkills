# Troubleshooting

## Can't attach: no sessions
- 会话可能已退出；重新 `tmux new` 创建并在里面跑任务。

## Keybindings don't work
- 你的前缀键默认是 `Ctrl-b`；如果被改过，检查 `~/.tmux.conf`。
