# 压缩与解压：gzip/xz 的常用选项与坑

## Goal
- 用 gzip/xz 压缩与解压文件，选择合适的参数，并在需要时保留原文件以便回滚。

## When to use
- 需要压缩日志/数据文件以节省空间或便于传输
- 需要解压 `.gz`/`.xz` 文件并保留原件

## When NOT to use
- 已经在 tar 里做了压缩且不需要二次压缩（避免浪费 CPU）
- 对随机数据（加密/压缩过的文件）再次压缩（收益很低）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件有读写权限（生成压缩文件）
- Tools: `gzip`/`gunzip`, `xz`/`unxz`
- Inputs needed: 目标文件路径与期望的压缩格式（gz/xz）

## Steps (<= 12)
1. gzip 压缩且保留原文件：`gzip -k <file>`（生成 `<file>.gz`）[[1][2]]
2. gzip 解压且保留压缩包：`gzip -dk <file>.gz`（等价 `gunzip -k`）[[1][2]]
3. 查看 gzip 压缩包信息：`gzip -l <file>.gz`（原始大小/压缩后大小）[[1][2]]
4. xz 压缩且保留原文件：`xz -k <file>`（更高压缩率可加 `-9e`；并行可加 `-T0`）[[3]]
5. xz 解压且保留压缩包：`xz -dk <file>.xz`（等价 `unxz -k`）[[3]]

## Verification
- 解压后文件大小合理；必要时用 `sha256sum` 对比压缩前后的内容一致性
- `gzip -t <file>.gz` 可做完整性测试（通过则退出码为 0）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 默认 `gzip <file>` 会替换原文件；建议用 `-k` 保留原件
- Privacy/credential handling: 压缩包仍包含原始数据；分享前确认不包含敏感信息
- Confirmation requirement: 不确定时先用 `-k`；批量压缩前先对小样本验证输出与命名

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: gzip(1): https://man.archlinux.org/man/gzip.1.en.txt
- [2] Arch Wiki: Archiving and compression: https://wiki.archlinux.org/title/Archiving_and_compression
- [3] Arch man: xz(1): https://man.archlinux.org/man/xz.1.en.txt
