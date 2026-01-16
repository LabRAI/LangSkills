# systemd 服务管理：systemctl 状态/启动/重启/自启

## Goal
- 用 `systemctl` 查看服务状态、启动/停止/重启、设置自启，并在变更前后做最小验证。

## When to use
- 服务启动失败/频繁重启，需要快速看 status 与原因
- 需要在机器重启后保持服务自启
- 做发布/变更后需要安全重启服务

## When NOT to use
- 你不确定这台机器的业务窗口且准备重启关键服务（先确认影响与回滚）

## Prerequisites
- Environment: Linux with systemd
- Permissions: 通常需要 sudo/root 管理 systemd system units（用户级 unit 另说）
- Tools: `systemctl`（可选 `journalctl` 配合看日志）
- Inputs needed: unit 名称（例如 `nginx.service`）

## Steps (<= 12)
1. 查看状态：`systemctl status <unit>`（关注 Active、Main PID、最近错误）[[1]]
2. 启动/停止/重启：`systemctl start|stop|restart <unit>`（尽量选低峰期）[[1]]
3. 重载配置（支持时）：`systemctl reload <unit>`（比 restart 更温和）[[1]]
4. 设置自启：`systemctl enable --now <unit>`；取消：`systemctl disable --now <unit>`[[1]]
5. 查看 unit 定义：`systemctl cat <unit>`；理解关键字段（ExecStart/Restart/依赖关系）[[1][2][3]]
6. 看失败列表：`systemctl --failed`；按需 `reset-failed` 清理失败状态（谨慎）[[1]]

## Verification
- `systemctl is-active <unit>` 为 active；`systemctl is-enabled <unit>` 符合预期
- 对外服务用 curl/端口探测做一次端到端验证

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 重启/停止关键服务会造成中断；错误的 enable/disable 会影响重启后行为
- Privacy/credential handling: status/journal 输出可能包含路径与参数；分享前脱敏
- Confirmation requirement: 高风险操作（stop/restart/enable）前确认影响范围与回滚方案；优先 reload；生产环境需变更记录

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: systemctl(1): https://man.archlinux.org/man/systemctl.1.en.txt
- [2] Arch man: systemd.service(5): https://man.archlinux.org/man/systemd.service.5.en.txt
- [3] Arch man: systemd.unit(5): https://man.archlinux.org/man/systemd.unit.5.en.txt
