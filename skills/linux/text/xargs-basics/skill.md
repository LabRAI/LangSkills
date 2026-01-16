# 批量执行命令：xargs 的安全模式（-0/-n/-P）

## Goal
- 用 xargs 把 stdin 的多行输入转成命令参数，并用 -0/-n/-P 等选项提高安全性与可控性。

## When to use
- 需要把一列路径/ID 批量喂给某个命令
- 需要限制每次参数数量或并行执行

## When NOT to use
- 输入包含复杂转义且无法保证分隔符（优先用 `-print0`/`-0` 或改用 `-exec ... {} +`）
- 对不可逆命令做批量执行但没有预览（先 echo/dry-run）

## Prerequisites
- Environment: Linux shell
- Permissions: 取决于将要执行的命令（xargs 本身只读 stdin）
- Tools: `xargs`（以及将要运行的目标命令）
- Inputs needed: 输入列表（stdin）、目标命令、每次处理多少项、是否并行

## Steps (<= 12)
1. 基础用法：`printf '%s\\n' a b c | xargs echo`[[1][2]]
2. 限制每次参数数量：`printf '%s\\n' a b c | xargs -n 1 echo`[[1][2]]
3. 使用占位符：`printf '%s\\n' a b | xargs -I{} echo "item={}"`[[2]]
4. 处理包含空格的路径：`find . -type f -print0 | xargs -0 -n 1 echo`（搭配 -print0/-0）[[2][3]]
5. 并行（谨慎）：`printf '%s\\n' a b c | xargs -P 4 -n 1 echo`（确保目标命令可并发）[[2]]
6. 对不可逆命令先预览：把 `echo` 换成真实命令前，先确认输出与数量（例如先 `wc -l`）[[2]]

## Verification
- 先用 `echo` 验证将执行的命令参数是否正确
- 对实际命令执行前后统计输入/输出数量（例如 `wc -l`）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: xargs 常用于执行命令，危险性取决于目标命令（rm/chmod 等）
- Privacy/credential handling: stdin 列表可能包含敏感路径/ID；记录日志时注意脱敏
- Confirmation requirement: 先 echo；优先使用 `-0` 处理路径；对高风险命令要求交互确认或小批量执行

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] POSIX xargs: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/xargs.html
- [2] man7 xargs(1): https://man7.org/linux/man-pages/man1/xargs.1.html
- [3] GNU findutils manual (find): https://www.gnu.org/software/findutils/manual/html_mono/find.html
