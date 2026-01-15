# 环境变量与 PATH：查看、临时设置、持久化与避坑

## Goal
- 查看与管理环境变量（尤其是 PATH），支持临时设置与持久化，并避免泄露敏感变量。

## When to use
- 命令找不到（PATH 问题）或需要临时注入配置（ENV vars）
- 需要为单条命令设置不同的变量值（不污染全局）

## When NOT to use
- 需要长期系统级配置但不了解 shell 初始化文件（先确认 bash/zsh 与加载顺序）
- 变量包含凭据且准备截图/复制到公开渠道（先脱敏）

## Prerequisites
- Environment: Linux shell (bash/zsh)
- Permissions: 一般不需要特殊权限；修改系统级配置可能需要 sudo
- Tools: `env`, shell builtin `export`
- Inputs needed: 要查看/设置的变量名（例如 PATH/HTTP_PROXY）与作用范围（一次命令/当前会话/持久化）

## Steps (<= 12)
1. 查看当前环境变量：`env | sort`（不要把输出直接发到公开渠道）[[1][2]]
2. 查看某个变量：`echo "$PATH"` 或 `env | rg '^PATH='`[[3]]
3. 为单条命令临时设置变量：`VAR=value command ...` 或 `env VAR=value command ...`[[1][2]]
4. 在当前 shell 会话生效：`export VAR=value`（新开终端不会保留）[[3]]
5. 追加 PATH（避免覆盖）：`export PATH="$PATH:/opt/bin"`[[3]]
6. 验证生效：`command -v <tool>` 或 `which <tool>`（确认解析到期望路径）[[3]]

## Verification
- `command -v <tool>` 指向期望路径
- 重新开一个 shell 后仍生效（如果做了持久化配置）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 错误修改 PATH 可能导致命令解析异常；通常可通过恢复配置回滚
- Privacy/credential handling: env 输出可能包含 token/密钥；共享前必须清理敏感变量
- Confirmation requirement: 改动前先记录原值；优先以追加方式修改 PATH，而不是覆盖

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 env(1): https://man7.org/linux/man-pages/man1/env.1.html
- [2] POSIX env: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/env.html
- [3] GNU Bash manual: https://www.gnu.org/software/bash/manual/bash.html
