# Edge cases

- 超大文件优先用 `tail -n`/`less`，避免 `cat` 全量输出。
- 日志里可能有 ANSI 颜色码；需要时用 `less -R`（谨慎）。
