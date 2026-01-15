# 连通性诊断：ping/traceroute（或 tracepath）

## Goal
- 用 `ping` 判断是否可达/是否丢包，用 `traceroute/tracepath` 定位网络路径中哪一跳出现问题。

## When to use
- 服务不可达（超时/连接失败）需要先判断网络层问题
- 需要区分“本机->网关->公网->目标”哪一段有问题

## When NOT to use
- 目标明确禁止 ICMP（ping 不通不代表 TCP 不通）
- 在对方网络做高频探测（避免被判为攻击）

## Prerequisites
- Environment: Linux shell
- Permissions: 某些系统对 ping 需要特权（依发行版而定）；traceroute 某些模式可能需要权限
- Tools: `ping` / `traceroute` / `tracepath`
- Inputs needed: 目标主机名或 IP

## Steps (<= 12)
1. 基础可达性：`ping -c 4 <host>`（看丢包率与 RTT）[[1]]
2. 控制等待/次数：`ping -c 10 -W 2 <host>`（减少长时间阻塞）[[1]]
3. 路径定位：`traceroute -n <host>`（-n 不做 DNS 解析更快更稳定）[[2]]
4. 必要时改用 ICMP：`traceroute -I -n <host>`（在 UDP 被屏蔽时尝试）[[2]]
5. traceroute 受限时：`tracepath <host>`（无需特权，输出 MTU/路径信息）[[3]]

## Verification
- 问题修复后 ping 丢包下降、RTT 恢复正常；traceroute 不再卡在某一跳
- 再用应用层验证（curl/ssh）确认服务恢复

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（探测型命令）
- Privacy/credential handling: 对外发包会暴露你的源 IP 与探测行为；在敏感环境遵循安全策略
- Confirmation requirement: 控制频率与次数（-c）；避免长时间高频 ping

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: ping(8): https://man.archlinux.org/man/ping.8.en.txt
- [2] Arch man: traceroute(8): https://man.archlinux.org/man/traceroute.8.en.txt
- [3] Arch man: tracepath(8): https://man.archlinux.org/man/tracepath.8.en.txt
