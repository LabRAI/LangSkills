# 列切分与拼接：cut/paste 处理 CSV/TSV 的常用套路

## Goal
- 用 cut/paste 对行文本做按列切分与拼接，快速处理简单 CSV/TSV/日志字段。

## When to use
- 日志/TSV/简单 CSV 需要提取少数列
- 需要把两个一列文件按行合并成多列表

## When NOT to use
- 复杂 CSV（引号、转义、嵌套逗号）需要真正的 CSV parser
- 字段是结构化 JSON（优先用 jq 等）

## Prerequisites
- Environment: Linux shell
- Permissions: 对输入文件有读权限；对输出路径有写权限
- Tools: `cut`, `paste`
- Inputs needed: 输入文件与分隔符（如逗号/制表符），以及要提取/拼接的列号

## Steps (<= 12)
1. 按分隔符提取字段：`cut -d',' -f1,3 data.csv`（取第 1 与第 3 列）[[1][3]]
2. TSV（tab）常用：`cut -f2-4 data.tsv`（默认分隔符为 tab）[[1][3]]
3. 按字符位置切片：`cut -c1-12 file.txt`（例如取固定宽度前 12 个字符）[[1][3]]
4. 把两列文件按行拼接：`paste -d',' col1.txt col2.txt > merged.csv`[[2]]
5. 把多行合并到一行：`paste -sd',' file.txt`（把所有行用逗号拼起来）[[2]]

## Verification
- 抽样检查输出列是否对齐（尤其是 CSV/TSV）
- 对固定宽度切片，确认字段位置没有漂移（避免误切）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（建议输出到新文件）
- Privacy/credential handling: 提取后的列可能仍包含敏感字段；共享前做脱敏/去标识化
- Confirmation requirement: 对生产数据先用少量行（`head`）验证分隔符与列号正确，再跑全量

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 cut(1): https://man7.org/linux/man-pages/man1/cut.1.html
- [2] man7 paste(1): https://man7.org/linux/man-pages/man1/paste.1.html
- [3] GNU coreutils manual (cut): https://www.gnu.org/software/coreutils/manual/html_node/cut-invocation.html
