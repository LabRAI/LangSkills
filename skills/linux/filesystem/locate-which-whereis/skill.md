# 用 locate/which/whereis/type 快速定位命令与路径

## Goal
- 快速定位命令/文件位置，并确认 shell 最终会执行哪个候选。

## When to use
- 同名命令很多，需要确认实际执行路径
- 需要快速定位文件/二进制/文档位置

## When NOT to use
- 你已经持有明确的绝对路径且不涉及 shell 解析

## Prerequisites
- Environment: Linux shell (bash/zsh)
- Permissions: 读取 PATH 目录与目标文件；locate 依赖数据库权限
- Tools: `command`/`type`，可选 `which`/`whereis`/`locate`
- Inputs needed: 命令名或文件名关键字

## Steps (<= 12)
1. 优先用可移植方式：`command -v <cmd>`（返回将被执行的路径或空）[[1]]
2. 查看所有解析结果（alias/function/builtin/path）：`type -a <cmd>`[[2]]
3. 只看 PATH 中可执行文件：`which -a <cmd>`[[3]]
4. 定位二进制/源码/manpage：`whereis <cmd>`；按文件名全盘找：`locate <name>`[[4][5]]
5. 验证：对 `command -v` 的路径做 `ls -l` / 运行 `<cmd> --version`（如适用）[[1]]

## Verification
- `command -v` 返回的路径与预期一致
- `type -a` 中没有意外的 alias/function 遮蔽

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（读操作）
- Privacy/credential handling: 输出路径可能包含用户名/项目名，分享前脱敏
- Confirmation requirement: 无

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU Bash manual (builtins: command/type): https://www.gnu.org/software/bash/manual/html_node/Bourne-Shell-Builtins.html
- [2] GNU Bash manual: https://www.gnu.org/software/bash/manual/bash.html
- [3] Arch man: which(1): https://man.archlinux.org/man/which.1.en.txt
- [4] Arch man: whereis(1): https://man.archlinux.org/man/whereis.1.en.txt
- [5] man7 locate(1): https://man7.org/linux/man-pages/man1/locate.1.html
