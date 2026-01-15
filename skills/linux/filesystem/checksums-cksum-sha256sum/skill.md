# 文件校验与完整性：cksum/sha256sum 的正确用法

## Goal
- 用校验和验证文件是否被篡改/损坏，并能把校验结果落盘以便后续复核。

## When to use
- 下载模型/数据集后需要验证完整性
- 在备份/迁移后需要确认文件未变化

## When NOT to use
- 把 checksum 当作“安全证明”（它只能验证一致性，不能替代签名/可信发布渠道）
- 对超大目录做全量校验但没有增量策略（先按关键文件/manifest 做）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件有读权限
- Tools: `sha256sum`（或同类 sha*sum）, `cksum`
- Inputs needed: 目标文件路径；可信渠道提供的 checksum（或自建 manifest）

## Steps (<= 12)
1. 为单个文件生成 SHA-256：`sha256sum <file> > <file>.sha256`[[1][3]]
2. 从校验文件验证：`sha256sum -c <file>.sha256`（应输出 `OK`）[[1][3]]
3. 对多文件生成 manifest：`sha256sum <file1> <file2> > checksums.sha256`[[1][3]]
4. 需要可移植校验时用 POSIX `cksum`：`cksum <file>`（记录 CRC 与 bytes）[[2]]
5. 对照可信渠道提供的 checksum（发布页/签名文件），确保算法一致（SHA-256 vs SHA-1 等）[[1][3]]

## Verification
- `sha256sum -c ...` 输出全部为 `OK`
- 对同一文件重复计算得到相同 checksum（未被修改）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无
- Privacy/credential handling: 校验 manifest 可能暴露文件名与目录结构；共享前去除敏感路径
- Confirmation requirement: 只从可信渠道获取 checksum/签名；不要在不可信页面复制粘贴可执行命令

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 sha256sum(1): https://man7.org/linux/man-pages/man1/sha256sum.1.html
- [2] POSIX cksum: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/cksum.html
- [3] GNU coreutils manual (cksum/sha*sum): https://www.gnu.org/software/coreutils/manual/coreutils.html
