# SSH 密钥登录：ssh-keygen + authorized_keys + ssh-agent

## Goal
- 生成 SSH 密钥、正确配置 `ssh-agent` 与 `authorized_keys`，用无密码（或带 passphrase）方式安全登录。

## When to use
- 你需要免密登录服务器/Git 仓库（推荐用 passphrase + agent）
- 你需要为某个自动化任务创建单独 key 并做最小授权

## When NOT to use
- 你准备把私钥粘贴到聊天/工单（绝对不要）
- 你不理解 key 的用途与权限边界（先学习，再操作）

## Prerequisites
- Environment: Linux shell / OpenSSH client
- Permissions: 本机写入 ~/.ssh；远端需要能修改目标用户的 ~/.ssh/authorized_keys
- Tools: `ssh-keygen` / `ssh-agent` / `ssh-add` / `ssh`（可选 `ssh-copy-id`）
- Inputs needed: 密钥用途（人用/CI）、注释（email/host）、远端 user@host（如需登录）

## Steps (<= 12)
1. 生成密钥（推荐 ed25519）：`ssh-keygen -t ed25519 -C '<comment>' -f ~/.ssh/id_ed25519`（建议设置 passphrase）[[1]]
2. 启动 agent 并加载 key：`eval "$(ssh-agent -s)"` 然后 `ssh-add ~/.ssh/id_ed25519`[[2]]
3. 把公钥安装到远端：`ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<host>`（或手动追加到 authorized_keys）[[3][4]]
4. 确认权限：`chmod 700 ~/.ssh`；远端 `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`[[3]]
5. 验证登录：`ssh -v <user>@<host>`（必要时看使用的 key/agent）[[2]]

## Verification
- `ssh <user>@<host>` 可直接登录且不会提示 password（或仅提示 passphrase/agent）
- 远端 `~/.ssh/authorized_keys` 只包含你期望的公钥

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 把错误的公钥写入 authorized_keys 可能造成越权；删除现有 key 可能导致你自己无法登录
- Privacy/credential handling: 私钥必须保密；公钥可公开但仍要避免把敏感注释/内部主机名暴露出去
- Confirmation requirement: 改动远端前先保留现有 authorized_keys 备份；确认至少保留一个可用登录方式（别锁死自己）

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: ssh-keygen(1): https://man.archlinux.org/man/ssh-keygen.1.en.txt
- [2] Arch man: ssh-agent(1): https://man.archlinux.org/man/ssh-agent.1.en.txt
- [3] Debian man: authorized_keys(5): https://manpages.debian.org/bookworm/openssh-server/authorized_keys.5.en.html
- [4] Arch man: ssh-copy-id(1): https://man.archlinux.org/man/ssh-copy-id.1.en.txt
