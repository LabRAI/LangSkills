# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。
> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹与 license 审计字段用于审计。

## [1]
- URL: https://man7.org/linux/man-pages/man1/sha256sum.1.html
- Accessed: 2026-01-15
- Summary: sha256sum(1) 生成与校验 SHA-256 校验和（-c 校验文件）。
- Supports: Steps 1-3,5
- License: unknown
- Fetch cache: miss
- Fetch bytes: 9900
- Fetch sha256: 95384c79724264fbf0f3f70bcc68305c5df5d50e00318e8c163a5c5ac70d9902

## [2]
- URL: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/cksum.html
- Accessed: 2026-01-15
- Summary: POSIX `cksum`（CRC + bytes），适合可移植的完整性校验与比对。
- Supports: Steps 4-5
- License: unknown
- Fetch cache: miss
- Fetch bytes: 18694
- Fetch sha256: b3d2f65a400fd99e46f3d64be4a40507af145e2c761597da2fa9052c416f2075

## [3]
- URL: https://www.gnu.org/software/coreutils/manual/coreutils.html
- Accessed: 2026-01-15
- Summary: coreutils 中 checksum 工具的用法与注意事项（含校验模式）。
- Supports: Steps 1-5
- License: unknown
- Fetch cache: hit
- Fetch bytes: 2149264
- Fetch sha256: ad5e6371eb4b4afaa20fcd7dcb30a36cc27c0706f26c6f50586c275b8e4c68a7
