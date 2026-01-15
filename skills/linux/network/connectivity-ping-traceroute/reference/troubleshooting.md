# Troubleshooting

## ping fails but service still works
- 目标可能禁 ICMP；改用应用层探测（例如 `curl -I` 或 `nc`/`ss`）。

## traceroute shows * * *
- 中间路由器可能不回 TTL exceeded；不代表一定故障。结合应用层与多地对比。
