# 打包与解包：tar（含 gzip/xz）最佳实践

## Goal
- 用 `tar` 安全地打包/解包目录（含 gzip/xz），并在解压前做内容预览与风险控制。

## When to use
- 需要把目录打包传输/备份（保留相对路径结构）
- 需要解压别人提供的 tar 包（先预览再落盘）

## When NOT to use
- 解压来源不可信且你无法在隔离目录中操作（先在沙箱/临时目录处理）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标目录有读权限（解压写入需要写权限）
- Tools: `tar`（可选 `gzip`/`xz`）
- Inputs needed: 要打包的路径或待解压的 archive 路径 + 目标目录

## Steps (<= 12)
1. 创建 tar.gz（推荐用 -C 控制相对路径）：`tar -C <base> -czf out.tar.gz <paths...>`[[1][2][3]]
2. 解压前先预览：`tar -tzf out.tar.gz | head`（确认没有绝对路径或 `..`）[[1][2]]
3. 解压到指定目录：`tar -xzf out.tar.gz -C <dest>`（尽量先解到空目录）[[1][2][3]]
4. xz 压缩：创建 `tar -cJf out.tar.xz ...`；解压 `tar -xJf out.tar.xz -C <dest>`[[1][2]]
5. 需要丢弃顶层目录时用：`--strip-components=1`（先预览确认层级）[[1][2]]

## Verification
- 解压后检查关键文件是否存在且大小合理：`ls -lah <dest>`
- 必要时对关键文件做校验（hash/文件数对比）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 解压可能覆盖现有文件；不可信 archive 可能包含路径穿越（`../`）或绝对路径
- Privacy/credential handling: 打包前确认不包含密钥/凭据/日志；必要时先清理或用排除规则
- Confirmation requirement: 解压前必须先 `tar -t` 预览；优先解到空目录；对不可信内容在隔离环境处理

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: tar(1): https://man.archlinux.org/man/tar.1.en.txt
- [2] GNU tar manual: https://www.gnu.org/software/tar/manual/html_node/index.html
- [3] man7 tar(1): https://man7.org/linux/man-pages/man1/tar.1.html
