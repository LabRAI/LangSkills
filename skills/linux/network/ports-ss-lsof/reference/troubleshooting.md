# Troubleshooting

## ss shows no process name
- 需要权限：加 sudo；或系统限制进程信息暴露。

## Port is used but not LISTEN
- 可能是客户端连接或 TIME_WAIT；检查 `ss -antup` 并理解连接状态。
