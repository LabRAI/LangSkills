# Troubleshooting

## No logs shown
- 可能没有权限；用 sudo 或加入日志读取组；确认服务是否真的写入 journald。

## Logs rotated / missing
- 检查 journald 的持久化设置与容量限制；必要时调整配置并重启 journald（需谨慎）。
