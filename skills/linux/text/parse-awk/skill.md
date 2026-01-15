# 结构化文本处理：awk 提取列、统计、聚合

## Goal
- 用 `awk` 对“按行记录、按列字段”的文本做提取、过滤与简单聚合（不写复杂脚本也能解决 80%）。

## When to use
- 从 `ps`/`df`/日志等输出中提取列并做统计
- 处理 CSV/TSV/空格分隔表格并导出某些字段

## When NOT to use
- 需要复杂 JSON/嵌套结构解析（优先用 `jq`）
- 需要大型数据处理/联表（优先用专用工具或脚本语言）

## Prerequisites
- Environment: Linux shell
- Permissions: 读取输入文件/命令输出
- Tools: `awk`
- Inputs needed: 输入文本（文件或管道）+ 目标字段/过滤条件/统计需求

## Steps (<= 12)
1. 打印列：`awk '{print $1, $3}' <file>`[[1][3]]
2. 指定分隔符：`awk -F',' '{print $1, $2}' data.csv`[[1][2]]
3. 过滤：`awk '$3 > 100 {print $1, $3}' <file>`[[1]]
4. 跳过表头：`awk 'NR==1{next} {print $0}' <file>`[[1]]
5. 聚合：`awk '{sum+=$2} END{print sum}' <file>`（可配合 -v 传参）[[1][2]]

## Verification
- 抽样输出确认列选择正确；必要时先 `head` 小样本再跑全量
- 用 `wc -l` 或手算对照验证统计结果是否合理

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读/输出操作；除非你把输出重定向覆盖原文件）
- Privacy/credential handling: 避免把包含用户数据的整行输出到公开渠道；优先输出必要字段
- Confirmation requirement: 对生产日志/大文件先用 `head`/小范围验证 awk 逻辑再全量跑

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] POSIX awk specification: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/awk.html
- [2] GNU gawk manual: https://www.gnu.org/software/gawk/manual/gawk.html
- [3] Arch man: awk(1): https://man.archlinux.org/man/awk.1.en.txt
