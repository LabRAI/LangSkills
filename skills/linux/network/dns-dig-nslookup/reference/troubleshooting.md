# Troubleshooting

## NXDOMAIN vs SERVFAIL
- NXDOMAIN：域名不存在或查询类型不对；SERVFAIL：上游/递归解析失败或 DNSSEC 等问题（需要换 resolver 对比）。

## Different answers in different networks
- 可能是 split-horizon DNS 或 CDN；用 `dig @<server>` 固定 resolver 再判断。
