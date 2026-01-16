# Edge cases

- 容器/最小系统可能不使用 journald；需要改用文件日志。
- `--since` 的解析依实现而定；不确定时用明确时间戳（ISO）。
