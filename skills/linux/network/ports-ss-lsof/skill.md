# 端口与进程：ss/lsof 找出谁在监听哪个端口

## Goal
- 用 `ss`/`lsof` 找出“谁在监听某个端口/谁占用某个连接”，用于端口冲突与服务排查。

## When to use
- 服务启动失败提示端口被占用
- 需要确认某端口是否在监听、由哪个进程监听
- 排查异常连接数或可疑监听端口

## When NOT to use
- 你准备直接 kill 进程但不确定影响范围（先确认服务归属与依赖）

## Prerequisites
- Environment: Linux shell
- Permissions: 查看进程信息通常需要 sudo（尤其是 -p 显示进程）
- Tools: `ss` / `lsof` / `fuser`
- Inputs needed: 端口号（TCP/UDP）或服务名

## Steps (<= 12)
1. 列出监听端口：`ss -lntup`（TCP/UDP + 进程）[[1]]
2. 按端口过滤：`ss -lntup 'sport = :443'`（或先全量再 grep）[[1]]
3. 用 lsof 定位监听者：`sudo lsof -i :443 -sTCP:LISTEN -nP`[[2]]
4. 快速拿 PID：`sudo fuser -n tcp 443`（谨慎使用后续 kill）[[3]]
5. 验证修复：停止/调整服务后重新 `ss -lntup` 确认端口状态变化[[1]]

## Verification
- 目标端口的监听进程与期望一致（或已释放）
- 应用层访问（curl/浏览器）验证服务恢复

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: kill 错进程可能造成服务中断；端口调整可能影响依赖方
- Privacy/credential handling: 连接信息可能包含内网 IP/端口；分享前脱敏
- Confirmation requirement: 在 kill 前先确认 PID 对应的服务与 owner；优先用 systemctl 停服务而不是直接 kill

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: ss(8): https://man.archlinux.org/man/ss.8.en.txt
- [2] Arch man: lsof(8): https://man.archlinux.org/man/lsof.8.en.txt
- [3] Arch man: fuser(1): https://man.archlinux.org/man/fuser.1.en.txt
