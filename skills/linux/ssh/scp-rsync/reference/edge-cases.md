# Edge cases

- rsync 源路径末尾 `/` 影响“同步目录本身 vs 同步目录内容”；先 dry-run 确认。
- 跨平台（macOS/Linux）权限/ACL 行为可能不同。
