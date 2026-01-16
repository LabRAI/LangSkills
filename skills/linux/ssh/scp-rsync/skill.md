# 文件传输：scp vs rsync（增量、断点、权限保留）

## Goal
- 在主机间安全传输文件：简单一次性用 `scp`，需要增量/断点/大目录同步优先用 `rsync`（带 dry-run）。

## When to use
- 复制少量文件到远端（scp 简单）
- 同步大目录/重复同步（rsync 更快更安全）
- 需要保留权限/时间戳并显示进度（rsync -aP）

## When NOT to use
- 你不确定源/目标路径是否正确且准备带 `--delete`（高风险）

## Prerequisites
- Environment: Linux shell / SSH
- Permissions: 远端目标路径写权限；SSH 登录权限
- Tools: `scp` / `rsync` / `ssh`
- Inputs needed: 源路径 + 远端 user@host:dest（方向：push/pull）

## Steps (<= 12)
1. 单文件 scp：`scp <file> <user>@<host>:/path/`（反向拉取：把左右互换）[[1]]
2. 目录 scp：`scp -r <dir> <user>@<host>:/path/`（适合一次性拷贝）[[1]]
3. 增量同步 rsync：`rsync -avP -e ssh <src>/ <user>@<host>:<dest>/`（注意尾部 `/`）[[2][3]]
4. 先 dry-run：`rsync -avP --dry-run -e ssh <src>/ <user>@<host>:<dest>/`[[2][3]]
5. 谨慎删除同步：仅在确认目标目录无独立数据时使用 `--delete`（建议先 dry-run）[[2][3]]

## Verification
- 在远端 `ls -lah <dest>` 抽样检查；或比较文件数/大小
- 重复跑 rsync 时应很快结束（说明增量生效）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: `rsync --delete` 可能删除目标文件；scp/rsync 也可能覆盖同名文件
- Privacy/credential handling: 传输前确认不包含密钥/凭据；必要时用加密/权限隔离
- Confirmation requirement: 任何涉及覆盖/删除的同步先 dry-run；确认 rsync 的源/目标尾部 `/` 语义

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: scp(1): https://man.archlinux.org/man/scp.1.en.txt
- [2] Arch man: rsync(1): https://man.archlinux.org/man/rsync.1.en.txt
- [3] rsync official manpage (plain text): https://download.samba.org/pub/rsync/rsync.1
