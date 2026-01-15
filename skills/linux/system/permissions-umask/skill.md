# 默认权限：umask 的含义、常见值（022/077）与验证方法

## Goal
- 理解并设置默认文件/目录权限（umask），用可验证的方法确认新建文件权限符合预期。

## When to use
- 需要提升默认安全性（例如把新建文件默认变成 600/700）
- 排查新建文件权限不对的问题

## When NOT to use
- 你不确定系统/应用依赖默认权限（先在隔离环境验证）
- 把 umask 当作替代 ACL/权限管理（它只影响新建，不影响已有文件）

## Prerequisites
- Environment: Linux shell
- Permissions: 一般不需要 sudo；系统级配置可能需要管理员权限
- Tools: shell builtin `umask`
- Inputs needed: 期望的默认权限策略（例如 022/027/077）

## Steps (<= 12)
1. 查看当前 umask：`umask`（通常输出 022/027/077 等八进制）[[1][2]]
2. 解释规则：umask 是要屏蔽的权限位；新文件默认 666、新目录默认 777，再减去 umask[[1][2]]
3. 临时设置为常见值：`umask 022`（更宽松）或 `umask 077`（更严格）[[1][2]]
4. 验证：`rm -f t && touch t && stat -c '%a %n' t`（看新文件权限是否符合预期）[[2]]
5. 持久化到 shell：把 `umask 027`（或你的值）写入 `~/.bashrc`/`~/.profile`（按登录类型选择）[[3]]
6. 重新登录或 `source` 配置后再次验证：`umask && touch t2 && stat -c '%a %n' t2`[[3]]

## Verification
- 新建文件/目录权限符合预期（例如 022→644/755，077→600/700）
- 重启 shell 后仍保持（如果做了持久化）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 更改 umask 会影响之后新建文件权限，可能导致程序无法写入或协作失败
- Privacy/credential handling: 更严格的 umask（如 077）可减少误共享；但也可能阻碍组协作
- Confirmation requirement: 先在当前 shell 验证，再持久化；对团队协作环境先确认组权限策略

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] POSIX umask: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/umask.html
- [2] man7 umask(1p): https://man7.org/linux/man-pages/man1/umask.1p.html
- [3] GNU Bash manual: https://www.gnu.org/software/bash/manual/bash.html
