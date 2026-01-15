# 创建与管理链接：符号链接 vs 硬链接（ln）

## Goal
- 创建与验证符号链接/硬链接，并理解它们的差异与限制。

## When to use
- 需要给同一个文件提供多个路径入口（硬链接）
- 需要用一个路径指向另一个路径（符号链接）

## When NOT to use
- 你不希望链接随目标移动/删除而失效（符号链接可能变成 broken link）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标目录有写权限
- Tools: `ln`（可选 `ls`/`stat`）
- Inputs needed: target 路径与 link 名称

## Steps (<= 12)
1. 创建符号链接：`ln -s <target> <link>`[[1][3]]
2. 创建硬链接：`ln <existing_file> <new_link>`（通常要求同一文件系统）[[1][2]]
3. 验证：`ls -l <link>` / `ls -li <file> <link>`（看 inode 是否相同）[[3]]

## Verification
- 硬链接的 inode 相同；符号链接指向正确目标
- 使用链接访问文件无误

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 覆盖/替换链接可能改变依赖指向
- Privacy/credential handling: 链接可能暴露目录结构；共享前脱敏
- Confirmation requirement: 覆盖前先 `ls -l` 确认现状与目标

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU coreutils manual: ln invocation: https://www.gnu.org/software/coreutils/manual/html_node/ln-invocation.html
- [2] POSIX ln specification: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/ln.html
- [3] Arch man: ln(1): https://man.archlinux.org/man/ln.1.en.txt
