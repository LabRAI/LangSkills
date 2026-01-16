# Troubleshooting

## status shows exit-code / failed
- 结合 `journalctl -u <unit>` 查看详细日志；检查 ExecStart、配置文件与依赖。

## Service keeps restarting
- 可能配置了 Restart=always/on-failure；先看 `systemctl cat <unit>`，再修复根因而不是一直重启。
