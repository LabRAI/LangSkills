# 文件复制与移动：cp/mv 的覆盖、保留属性与安全预览

## Goal
- 安全地复制/移动文件与目录，避免意外覆盖，并在需要时保留权限与时间戳。

## When to use
- 需要复制文件/目录到新位置，或批量重命名/移动
- 需要避免覆盖或需要保留权限/时间戳/符号链接语义

## When NOT to use
- 跨机器或大目录增量同步（优先用 `rsync`）
- 目标路径不确定、可能覆盖关键文件（先做 dry-run 列表/备份）

## Prerequisites
- Environment: Linux shell
- Permissions: 对源路径有读权限，对目标目录有写权限
- Tools: `cp`, `mv`
- Inputs needed: 源路径、目标路径（以及是否允许覆盖/是否需要保留属性）

## Steps (<= 12)
1. 复制单个文件并避免覆盖：`cp -n <src> <dst>`（必要时用 `-i` 交互确认）[[1][3]]
2. 复制目录并保留属性：`cp -a <src_dir> <dst_dir>`（比 `cp -r` 更安全，保留权限/时间戳/链接语义）[[1][3]]
3. 需要查看将复制什么时，用 `-v` 输出计划：`cp -av <src_dir> <dst_dir>`[[1][3]]
4. 要保留被覆盖前的旧版本，使用备份：`cp --backup=numbered <src> <dst>`（或 `--backup=t`）[[1][3]]
5. 移动/重命名时避免覆盖：`mv -n <old> <new>`（不确定时用 `mv -i`）[[2][3]]
6. 完成后验证：用 `ls -l`/`stat` 检查权限/时间戳；必要时用 `diff -q <src> <dst>` 抽样比对内容[[1][2][3]]

## Verification
- 检查是否意外覆盖：`ls -l <dst>`（时间戳/大小是否合理）
- 抽样比对：`diff -q <src> <dst>` 或 `cmp <src> <dst>`

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 覆盖（overwrite）可能导致数据丢失；移动会改变原路径位置
- Privacy/credential handling: 避免把含密钥/凭据的文件复制到不安全位置或提交到版本库
- Confirmation requirement: 默认用 `-n` 或 `-i`；关键路径先备份（`--backup=numbered`）再批量操作

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: cp(1): https://man.archlinux.org/man/cp.1.en.txt
- [2] Arch man: mv(1): https://man.archlinux.org/man/mv.1.en.txt
- [3] Arch Wiki: Core utilities: https://wiki.archlinux.org/title/Core_utilities
