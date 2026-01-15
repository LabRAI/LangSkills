# Edge cases

- 用户级 unit（systemctl --user）与系统级 unit 行为不同；权限与路径也不同。
- 修改 unit 文件后需要 `systemctl daemon-reload` 才生效（谨慎）。
