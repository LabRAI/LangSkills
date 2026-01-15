# Edge cases

- 不同 find 实现（GNU find vs busybox find）可能在部分选项上有差异；以 `find --help` / man page 为准。
- `-exec ... {} +` 与 `-exec ... {} \;` 行为不同（批量 vs 单个）。
