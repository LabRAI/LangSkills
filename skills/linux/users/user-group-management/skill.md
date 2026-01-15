# 用户与组管理：useradd/usermod/groups（含 sudo 组）

## Goal
- 安全地创建/修改用户与用户组：用 useradd/usermod/groupadd 管理账号，用 id 验证组成员关系（含 sudo 组）。

## When to use
- 新建服务账号/开发账号
- 给现有用户追加组权限（例如读日志组、docker 组）
- 排查权限问题时确认用户实际组列表

## When NOT to use
- 你准备给用户加 sudo/管理员权限但未走审批（高风险）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常需要 sudo/root
- Tools: `useradd` / `usermod` / `groupadd` / `id`（可选 `passwd`）
- Inputs needed: 用户名 + 需要加入的组（是否需要 sudo）

## Steps (<= 12)
1. 检查现有用户/组：`id <user>`（确认当前 groups）[[4]]
2. 创建用户：`sudo useradd -m -s /bin/bash <user>`（-m 创建 home）[[1]]
3. 创建组（如需要）：`sudo groupadd <group>`[[3]]
4. 把用户加入附加组：`sudo usermod -aG <group> <user>`（不要漏 -a）[[2]]
5. 需要 sudo 权限时：加入发行版的 admin 组（常见是 `sudo` 或 `wheel`）并遵循最小授权原则[[2]]
6. 验证：重新 `id <user>`；必要时让用户重新登录使组变更生效[[4]]

## Verification
- `id <user>` 显示期望的 groups
- 以该用户实际执行一次目标操作（读写目录/运行命令）验证权限已生效

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 给错组（尤其 sudo/wheel）会造成越权；删除/修改用户可能影响服务与数据所有权
- Privacy/credential handling: 账号信息属于敏感资产；公开记录时避免暴露内部用户名规则
- Confirmation requirement: 涉及 sudo/wheel 必须审批；变更前后记录 `id` 输出与变更原因；避免直接改现网关键账号

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: useradd(8): https://man.archlinux.org/man/useradd.8.en.txt
- [2] Arch man: usermod(8): https://man.archlinux.org/man/usermod.8.en.txt
- [3] Arch man: groupadd(8): https://man.archlinux.org/man/groupadd.8.en.txt
- [4] Arch man: id(1): https://man.archlinux.org/man/id.1.en.txt
