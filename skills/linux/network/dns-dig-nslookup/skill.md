# DNS 排查：dig/nslookup 看解析链路与 TTL

## Goal
- 用 `dig`/`nslookup` 排查 DNS：看解析结果、TTL、CNAME 链路，并对比不同解析服务器。

## When to use
- 域名解析异常/不一致（不同网络返回不同 IP）
- 需要确认某条记录是否已生效（TTL/缓存）
- 排查反向解析或 DNS 服务器配置问题

## When NOT to use
- 问题不在 DNS（例如 TCP 连接被防火墙阻断）
- 域名为内部敏感域（避免在公共 DNS 上泄露）

## Prerequisites
- Environment: Linux shell
- Permissions: 无（只读查询；读 /etc/resolv.conf 需要可读）
- Tools: `dig` / `nslookup`（通常来自 bind-tools）
- Inputs needed: 域名或 IP + 期望记录类型（A/AAAA/CNAME/TXT/MX）+ 可选 DNS 服务器

## Steps (<= 12)
1. 快速看 A/AAAA：`dig example.com A +short` / `dig example.com AAAA +short`[[1]]
2. 指定解析服务器对比：`dig @1.1.1.1 example.com A +short`（或公司 DNS）[[1]]
3. 看 CNAME 链与 TTL：`dig example.com CNAME`（answer 里带 TTL）[[1]]
4. 反向解析：`dig -x <ip> +short`[[1]]
5. 对比系统工具：`nslookup example.com`（快速 sanity check）[[2]]
6. 检查本机 resolver 配置：`cat /etc/resolv.conf`（nameserver/search/options）[[3]]

## Verification
- 对比不同解析器返回是否一致（A/AAAA/CNAME）
- 结合 TTL 判断缓存窗口；等待 TTL 后再验证生效

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读查询）
- Privacy/credential handling: DNS 查询会被解析器记录；内部域名尽量在内网 DNS 上查，不要在公共 DNS 上泄露
- Confirmation requirement: 无

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: dig(1): https://man.archlinux.org/man/dig.1.en.txt
- [2] Arch man: nslookup(1): https://man.archlinux.org/man/nslookup.1.en.txt
- [3] Arch Wiki: Resolv.conf: https://wiki.archlinux.org/title/Resolv.conf
