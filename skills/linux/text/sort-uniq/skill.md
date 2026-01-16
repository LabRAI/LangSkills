# 排序与去重：sort/uniq 的高频用法（含计数与按列排序）

## Goal
- 用 sort/uniq 做排序、去重、计数与按列排序，并避免常见陷阱（locale、uniq 需先排序）。

## When to use
- 需要对日志/列表排序或去重
- 需要统计重复项出现次数（Top-N）

## When NOT to use
- 数据量巨大且内存受限（考虑 `sort -T` 指定临时目录或用专门工具/数据库）
- 需要稳定的区域性排序但不理解 locale 影响（先固定 `LC_ALL=C`）

## Prerequisites
- Environment: Linux shell
- Permissions: 对输入文件有读权限；对输出路径有写权限
- Tools: `sort`, `uniq`
- Inputs needed: 输入文件（每行一条记录）与排序/去重规则（数值/字典序/按列等）

## Steps (<= 12)
1. 基础排序：`sort <in.txt> > sorted.txt`[[1][3]]
2. 数值排序：`sort -n numbers.txt`；人类可读数值（1K/10M）用 `sort -h`[[1][3]]
3. 按分隔符与列排序：`sort -t',' -k2,2 data.csv`（按第 2 列）[[1][3]]
4. 去重（推荐先排序）：`sort <in.txt> | uniq`；或直接用 `sort -u <in.txt>`[[1][2][3]]
5. 统计重复次数：`sort <in.txt> | uniq -c | sort -nr`（Top-N 可再加 `head`）[[2][3]]
6. locale 影响排序时，固定为字节序：`LC_ALL=C sort ...`（结果更可复现）[[1][3]]

## Verification
- 用 `sort -c sorted.txt` 检查是否已排序（通过则退出码为 0）
- 抽样查看排序/去重结果是否符合预期（尤其是按列排序）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（建议把输出重定向到新文件，避免覆盖原件）
- Privacy/credential handling: 对包含敏感数据的日志做排序/统计时，避免把输出上传到公开渠道
- Confirmation requirement: 如果要覆盖原文件，先写到临时文件并备份（例如 `mv -n`）

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 sort(1): https://man7.org/linux/man-pages/man1/sort.1.html
- [2] man7 uniq(1): https://man7.org/linux/man-pages/man1/uniq.1.html
- [3] GNU coreutils manual (sort/uniq): https://www.gnu.org/software/coreutils/manual/coreutils.html
