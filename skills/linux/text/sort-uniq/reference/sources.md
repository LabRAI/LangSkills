# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。
> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹与 license 审计字段用于审计。

## [1]
- URL: https://man7.org/linux/man-pages/man1/sort.1.html
- Accessed: 2026-01-15
- Summary: sort(1) 排序选项（-n/-h/-t/-k/-u 等）与行为说明。
- Supports: Steps 1-5
- License: GPL-3.0-or-later
- Fetch cache: miss
- Fetch bytes: 13524
- Fetch sha256: 80324fb0c2a7ec268b79b611775b7d11498de4326df97e5ff3b55f1efd9498b8

## [2]
- URL: https://man7.org/linux/man-pages/man1/uniq.1.html
- Accessed: 2026-01-15
- Summary: uniq(1) 去重与计数（-c/-d/-u），注意需要相邻重复（通常先 sort）。
- Supports: Steps 4-6
- License: GPL-3.0-or-later
- Fetch cache: miss
- Fetch bytes: 10101
- Fetch sha256: 8f66ddd0cdea21b19bef86d9052c890997b68202b5607676eb3f643d2b5a75e2

## [3]
- URL: https://www.gnu.org/software/coreutils/manual/coreutils.html
- Accessed: 2026-01-15
- Summary: coreutils 对 sort/uniq 的更完整说明（含 locale/稳定性等注意点）。
- Supports: Steps 1-6
- License: GFDL-1.3-or-later
- Fetch cache: hit
- Fetch bytes: 2149264
- Fetch sha256: ad5e6371eb4b4afaa20fcd7dcb30a36cc27c0706f26c6f50586c275b8e4c68a7
