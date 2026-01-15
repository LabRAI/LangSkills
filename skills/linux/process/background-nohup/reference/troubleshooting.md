# Troubleshooting

## No output appears in log
- 程序可能缓冲输出；确认是否写到 stderr/stdout；必要时调整程序日志参数或用行缓冲工具。

## Process dies after logout
- 确认用了 nohup 或 disown；某些环境还需要 tmux/systemd 才能稳定托管。
