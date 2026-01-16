# Troubleshooting

## dmesg: Operation not permitted
- 可能启用了 `dmesg_restrict`；用 sudo 或改用 `journalctl -k`（systemd 环境）。
