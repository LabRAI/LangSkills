# systemd 日志：journalctl 按服务/时间/级别过滤

## Goal
- 用 `journalctl` 快速定位 systemd 管理服务/系统的日志：按 unit、时间、boot、优先级过滤，并支持实时跟随。

## When to use
- 服务异常需要看日志（结合 systemctl status）
- 排查启动后某个时间窗口的错误/警告
- 需要抓取日志作为问题证据（注意脱敏）

## When NOT to use
- 日志包含敏感信息且你要直接公开（先脱敏/裁剪）

## Prerequisites
- Environment: Linux with systemd
- Permissions: 读取系统日志可能需要 sudo 或加入 systemd-journal 组（发行版不同）
- Tools: `journalctl`
- Inputs needed: unit 名称 + 时间范围（可选）

## Steps (<= 12)
1. 按服务看日志：`journalctl -u <unit> --no-pager`[[1][3]]
2. 实时跟随：`journalctl -u <unit> -f`[[1][3]]
3. 按时间窗口：`journalctl -u <unit> --since '1 hour ago' --until 'now'`[[1][3]]
4. 按 boot：`journalctl -b`（本次启动）或 `journalctl -b -1`（上次启动）[[1][3]]
5. 按优先级：`journalctl -p warning..err -u <unit>`（聚焦警告/错误）[[1][3]]
6. 输出格式：`-o short-iso` 或 `-o json-pretty`；必要时了解 journald 存储策略[[1][2][3]]

## Verification
- 能在日志中定位到报错时间点与关键堆栈/错误码，并与 status 对应
- 修复后再次 follow，确认错误不再出现

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读）
- Privacy/credential handling: 日志可能包含凭据、用户数据、路径；导出/分享前脱敏
- Confirmation requirement: 避免在公开渠道粘贴完整日志；只截取必要窗口并去标识化

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: journalctl(1): https://man.archlinux.org/man/journalctl.1.en.txt
- [2] Arch man: systemd-journald(8): https://man.archlinux.org/man/systemd-journald.8.en.txt
- [3] systemd docs: journalctl: https://www.freedesktop.org/software/systemd/man/journalctl.html
