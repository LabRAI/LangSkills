# 所有者与用户组：chown/chgrp 递归修改与安全边界

## Goal
- 用 `chown`/`chgrp` 正确设置文件属主与属组，避免递归误操作导致权限或服务问题。

## When to use
- 服务/容器需要把目录交给特定用户运行（例如 `www-data`/`nginx`）
- 项目目录需要共享给某个组并统一权限策略
- 修复“Permission denied”但权限位（chmod）本身无误的情况

## When NOT to use
- 你不清楚递归范围或目标目录里包含系统关键路径（先列清单）
- 在生产机上临时“试试看”解决问题（先做最小变更并记录）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常需要 sudo/root（或你是文件 owner）
- Tools: `chown` / `chgrp`（可选 `ls`/`stat`/`find`）
- Inputs needed: 目标路径 + 期望的 user[:group]（是否递归）

## Steps (<= 12)
1. 确认当前属主/属组：`ls -l <path>` 或 `stat -c '%U:%G %n' <path>`[[3]]
2. 只改属组（共享目录常用）：`chgrp <group> <path>`[[2]]
3. 改属主/属组：`chown <user>:<group> <path>`（只改属主可省略 `:<group>`）[[1][3]]
4. 递归前先做范围确认（dry-run 思路）：抽样列出子项并确认不会扫到挂载点/软链接树[[3]]
5. 递归修改（谨慎）：`chown -R <user>:<group> <dir>`；遇到符号链接按需选择 `-P/-H/-L`[[1][3]]
6. 验证：`ls -l <dir> | head`（必要时只抽样检查关键文件）[[3]]

## Verification
- 抽样 `ls -l` 确认属主/属组符合预期
- 以目标用户实际读写/启动一次服务验证问题已解决

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 错误的 owner/group 可能导致服务不可用或把敏感文件暴露给不该访问的用户/组
- Privacy/credential handling: 无（但变更记录中避免暴露敏感路径）
- Confirmation requirement: 递归操作前必须明确范围；优先在小目录试跑并抽样验证，再扩大范围

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU coreutils manual: chown invocation: https://www.gnu.org/software/coreutils/manual/html_node/chown-invocation.html
- [2] GNU coreutils manual: chgrp invocation: https://www.gnu.org/software/coreutils/manual/html_node/chgrp-invocation.html
- [3] Arch man: chown(1): https://man.archlinux.org/man/chown.1.en.txt
