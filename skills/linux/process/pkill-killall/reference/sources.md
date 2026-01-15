# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。
> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹与 license 审计字段用于审计。

## [1]
- URL: https://man7.org/linux/man-pages/man1/kill.1.html
- Accessed: 2026-01-15
- Summary: kill(1) 发送信号（TERM/KILL 等）到指定 PID。
- Supports: Steps 3-5
- License: unknown
- Fetch cache: miss
- Fetch bytes: 17660
- Fetch sha256: c23ee7ffe62b97a288589351445a7f1e3bc1f7358bf4972fdbe455e8ae4038f3

## [2]
- URL: https://man7.org/linux/man-pages/man1/pkill.1.html
- Accessed: 2026-01-15
- Summary: pkill/pgrep 按名称/模式匹配进程并发送信号（先 pgrep 再 pkill 更安全）。
- Supports: Steps 1-4
- License: unknown
- Fetch cache: miss
- Fetch bytes: 19899
- Fetch sha256: 8db22a08b2b3e16e134cf17a69672bdf8634cf223a4e8dd3f5e1ccb61db62144

## [3]
- URL: https://man7.org/linux/man-pages/man1/killall.1.html
- Accessed: 2026-01-15
- Summary: killall 按进程名终止（同名进程较多时风险更高）。
- Supports: Steps 2-5
- License: unknown
- Fetch cache: miss
- Fetch bytes: 13586
- Fetch sha256: fabe2afd639c99e8201675e59bf2d4fe5b6508bf97a427c60663dbe25e1b33b2
