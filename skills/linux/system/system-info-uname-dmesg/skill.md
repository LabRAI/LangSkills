# 系统信息与启动排查：uname/lsb_release/dmesg

## Goal
- 快速收集系统信息与启动/硬件相关日志：用 `uname`/`lsb_release` 标识系统，用 `dmesg` 定位内核级错误。

## When to use
- 需要提交 bug report/排查环境差异（内核版本、架构、发行版）
- 排查硬件/驱动/启动相关异常（dmesg）

## When NOT to use
- 日志包含敏感信息且你要发到公开渠道（先脱敏/只截取必要片段）

## Prerequisites
- Environment: Linux shell
- Permissions: 读取 dmesg 在某些系统可能需要 sudo（取决于 dmesg_restrict）
- Tools: `uname` / `dmesg`（可选 `lsb_release`）
- Inputs needed: 无（或你要排查的关键字：error/fail 等）

## Steps (<= 12)
1. 确认内核与架构：`uname -a`（或更简洁 `uname -srmo`）[[1]]
2. 确认发行版：`lsb_release -a`（若无该命令，可改用 `/etc/os-release`）[[2]]
3. 查看最近内核日志：`dmesg -T | tail -n 200`（带人类可读时间）[[3]]
4. 按关键字过滤：`dmesg -T | grep -i 'error\|fail\|warn' | tail -n 50`[[3]]

## Verification
- 把 uname/发行版信息与相关 dmesg 片段整理成问题描述，能复现/定位方向更明确

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读）
- Privacy/credential handling: dmesg 可能包含设备序列号、路径、内核参数等；公开前脱敏
- Confirmation requirement: 如需 sudo 查看 dmesg，先确认安全策略允许并避免把完整日志外发

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: uname(1): https://man.archlinux.org/man/uname.1.en.txt
- [2] Arch man: lsb_release(1): https://man.archlinux.org/man/lsb_release.1.en.txt
- [3] Arch man: dmesg(1): https://man.archlinux.org/man/dmesg.1.en.txt
