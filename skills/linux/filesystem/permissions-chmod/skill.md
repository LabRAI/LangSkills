# 文件权限入门：chmod 数字/符号写法与常见坑

## Goal
- 安全地修改文件/目录权限（chmod 符号/数字写法）。

## When to use
- 脚本需要可执行权限
- 修复权限过宽/过严导致的访问问题

## When NOT to use
- 你不确定递归修改影响范围（先列清单）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标是 owner 或具备 sudo
- Tools: `chmod`（可选 `find`）
- Inputs needed: 目标路径 + 期望权限（符号或数字）

## Steps (<= 12)
1. 查看当前权限：`ls -l <path>`[[3]]
2. 符号写法：`chmod u+x <script>` / `chmod go-rwx <file>`[[1][3]]
3. 数字写法常见：文件 `644`、目录 `755`（例如：`chmod 644 file`）[[1][2]]
4. 递归更谨慎：优先用 find 区分目录/文件再 chmod（避免目录被设成 644）[[1][3]]

## Verification
- 重新 `ls -l` 确认权限变化
- 实际执行/访问一次确认问题解决

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 权限过宽会引入安全风险；过严可能导致服务不可用
- Privacy/credential handling: 无
- Confirmation requirement: 递归操作前先列出目标清单并确认；生产环境需变更记录

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU coreutils manual: chmod invocation: https://www.gnu.org/software/coreutils/manual/html_node/chmod-invocation.html
- [2] man7 chmod(1): https://man7.org/linux/man-pages/man1/chmod.1.html
- [3] Arch man: chmod(1): https://man.archlinux.org/man/chmod.1.en.txt
