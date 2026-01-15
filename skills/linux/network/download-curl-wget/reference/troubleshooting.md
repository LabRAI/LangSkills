# Troubleshooting

## TLS/SSL errors
- 优先检查系统时间、CA 证书与代理；不要轻易用 `-k/--insecure`（会绕过验证）。

## 403/401 unauthorized
- 检查是否需要 token/header；避免把 token 直接写在命令行历史里。
