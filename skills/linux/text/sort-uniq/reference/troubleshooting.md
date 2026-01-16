# Troubleshooting

## uniq didn't remove duplicates
- `uniq` 只会合并相邻重复行；通常需要先 `sort`。

## Sort order looks wrong
- 检查是否用了 `-n`（数值）/ `-h`（人类可读）/ `-t/-k`（按列）。
- locale 影响时用 `LC_ALL=C` 固定排序规则。
