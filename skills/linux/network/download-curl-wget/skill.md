# 下载与 HTTP 调试：curl/wget（header、重试、代理）

## Goal
- 用 `curl`/`wget` 下载文件并调试 HTTP（查看 header、跟随重定向、重试、代理），同时避免泄露凭据。

## When to use
- 需要下载 artifact/数据集/脚本
- 需要排查 HTTP 状态码、重定向与 header
- 网络不稳定需要断点续传/重试策略

## When NOT to use
- 需要自动化认证/复杂会话管理（优先用专用 SDK 或脚本）
- 不确定 URL 是否可信（避免直接执行下载的脚本）

## Prerequisites
- Environment: Linux shell
- Permissions: 写入目标目录权限
- Tools: `curl` / `wget`
- Inputs needed: URL + 保存位置（可选：代理、header、认证方式）

## Steps (<= 12)
1. 最简单下载：`curl -LO <url>`（保留远端文件名）或 `wget <url>`[[1][2]]
2. 看响应头/状态码：`curl -I <url>`；需要更详细可用 `curl -v <url>`[[1][3]]
3. 跟随重定向：`curl -L -O <url>`；wget 可用 `--max-redirect` 控制[[1][2][3]]
4. 断点续传：`curl -C - -LO <url>`；wget 用 `-c`[[1][2][3]]
5. 重试/超时：`curl --retry 5 --retry-delay 1 --connect-timeout 5 --max-time 30 ...`；wget 用 `--tries/--timeout`[[1][2][3]]
6. 代理/自定义 header：`curl -x http://proxy:port -H 'Key: Value' ...`（避免把 token 写进 shell history）[[1][3]]

## Verification
- 下载后校验大小/哈希：`ls -lh` + `sha256sum`（如有官方 checksum）
- 用 `file`/`tar -t` 等验证文件格式是否正确

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 下载本身可逆，但“执行下载内容”可能造成不可逆后果
- Privacy/credential handling: 避免在命令行/日志中暴露 `Authorization`、cookie、token；必要时用环境变量或 `--config` 文件
- Confirmation requirement: 对不可信 URL 不要 `curl | sh`；先保存、审阅、再执行

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: curl(1): https://man.archlinux.org/man/curl.1.en.txt
- [2] Arch man: wget(1): https://man.archlinux.org/man/wget.1.en.txt
- [3] curl docs: manpage: https://curl.se/docs/manpage.html
