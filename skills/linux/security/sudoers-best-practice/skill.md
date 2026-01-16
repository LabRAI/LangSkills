# sudo 最佳实践：visudo 编辑 sudoers、最小授权与审计

## Goal
- 用 `visudo` 安全管理 sudo 授权：最小权限、可审计、避免把系统锁死或引入特权升级路径。

## When to use
- 需要让某个用户/组执行少量管理命令（最小授权）
- 需要为运维脚本配置受限 sudo 权限并可审计

## When NOT to use
- 你准备给人/脚本加 ALL=(ALL) NOPASSWD:ALL（极高风险）
- 你不确定 sudoers 语法且没有恢复通道（先在测试机验证）

## Prerequisites
- Environment: Linux with sudo installed
- Permissions: 需要已有管理员权限（root 或现有 sudo）
- Tools: `visudo` / `sudo`
- Inputs needed: 要授权的用户/组 + 允许的命令列表（尽量写绝对路径）

## Steps (<= 12)
1. 永远用 visudo 修改：`sudo visudo`；或写单独文件：`sudo visudo -f /etc/sudoers.d/<name>`[[2]]
2. 按最小权限写规则：限定到具体命令的绝对路径（避免通配/编辑器/解释器）[[1]]
3. 验证授权：`sudo -l -U <user>` 查看该用户可执行的 sudo 命令[[3]]
4. 上线前做一次实测：用目标用户执行被允许的命令；确保“未授权命令”仍被拒绝[[1][3]]

## Verification
- `sudo -l -U <user>` 输出符合预期且无多余权限
- 目标用户能执行被允许的命令、不能执行未允许的命令

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 错误 sudoers 可能导致你无法 sudo（锁死）或造成特权提升；NOPASSWD 可能被滥用
- Privacy/credential handling: sudoers 规则可能暴露内部路径/账号；分享前脱敏
- Confirmation requirement: 任何新增 sudo 权限必须审批+审计；高风险变更保留恢复通道（root 控制台/救援模式）

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: sudoers(5): https://man.archlinux.org/man/sudoers.5.en.txt
- [2] Arch man: visudo(8): https://man.archlinux.org/man/visudo.8.en.txt
- [3] Arch man: sudo(8): https://man.archlinux.org/man/sudo.8.en.txt
