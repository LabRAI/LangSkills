# 时间与时区：date 的格式化/解析、TZ 临时切换与一致性检查

## Goal
- 用 date 查看/格式化时间，临时切换时区（TZ），并做基础一致性检查（UTC vs local）。

## When to use
- 日志排查需要对齐时间窗口（UTC/local）
- 需要生成可排序的时间戳（ISO-8601/epoch）

## When NOT to use
- 需要修改系统时间（高风险，涉及 NTP/服务影响；需额外流程）
- 需要高精度时间同步（应使用专门的 NTP/chrony 工具与监控）

## Prerequisites
- Environment: Linux shell
- Permissions: 查看时间无需权限；修改系统时间通常需要 sudo
- Tools: `date`
- Inputs needed: 需要的输出格式（ISO/epoch/自定义）与时区（local/UTC/指定 TZ）

## Steps (<= 12)
1. 查看当前本地时间：`date`[[1][2][3]]
2. 输出 ISO-8601：`date -Iseconds`（更适合日志与机器处理）[[1][3]]
3. 查看 UTC：`date -u` 或 `TZ=UTC date`[[1][2][3]]
4. 自定义格式：`date '+%Y-%m-%d %H:%M:%S %z'`[[1][2][3]]
5. 临时切换时区：`TZ=America/New_York date`（只影响该命令）[[3]]

## Verification
- 对同一时刻，UTC 与 local 的差值符合预期时区偏移（%z）
- 用于文件命名的时间戳排序正确（字符串排序即时间顺序）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 查看时间无；但修改系统时间会影响任务调度与证书校验等（不要在这里做）
- Privacy/credential handling: 时间戳通常无隐私，但与其他信息组合可能暴露活动时间
- Confirmation requirement: 只做查看与格式化；如要改系统时间，必须走额外审批/回滚流程

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 date(1): https://man7.org/linux/man-pages/man1/date.1.html
- [2] POSIX date: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/date.html
- [3] GNU coreutils manual (date): https://www.gnu.org/software/coreutils/manual/coreutils.html
