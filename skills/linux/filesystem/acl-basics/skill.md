# ACL 权限：getfacl/setfacl 做精细授权

## Goal
- 用 `getfacl`/`setfacl` 为文件或目录提供更细粒度的授权（不必改变 owner/group 或全局 chmod）。

## When to use
- 需要让“额外的某个用户/组”访问某个目录，但不想改 owner/group
- 需要目录中新建文件自动继承权限（默认 ACL）

## When NOT to use
- 简单的 owner/group + chmod 就能解决（优先用最简单方案）
- 你无法维护 ACL 的复杂度（团队需要一致策略）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常需要 owner 或 sudo
- Tools: `getfacl` / `setfacl`
- Inputs needed: 目标路径 + 要授权的 user/group + 权限（r/w/x）

## Steps (<= 12)
1. 查看现状：`ls -ld <path>` 然后 `getfacl -p <path>`[[1]]
2. 给用户追加 ACL：`setfacl -m u:<user>:rw <file>` 或 `setfacl -m u:<user>:rwx <dir>`[[2]]
3. 给组追加 ACL：`setfacl -m g:<group>:rx <dir>`（注意 mask 可能限制“有效权限”）[[2][3]]
4. 目录默认 ACL（让新文件继承）：`setfacl -d -m u:<user>:rwx <dir>`[[2][3]]
5. 验证：再次 `getfacl -p <path>`，确认条目与 effective 权限符合预期[[1][3]]
6. 回滚：删单条 `setfacl -x u:<user> <path>`；清空 ACL `setfacl -b <path>`[[2]]

## Verification
- 用目标用户实测：`sudo -u <user> ls <path>` / `cat` / `touch`（按需求验证读写）
- 再次 `getfacl` 确认 ACL 已按预期生效或清理

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: ACL 可能扩大访问范围；误配会造成越权或泄露
- Privacy/credential handling: 避免在公开渠道分享包含用户/目录结构的 ACL 输出
- Confirmation requirement: 变更前先 `getfacl` 备份（输出到文件）；变更后用目标用户实测

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: getfacl(1): https://man.archlinux.org/man/getfacl.1.en.txt
- [2] Arch man: setfacl(1): https://man.archlinux.org/man/setfacl.1.en.txt
- [3] Arch Wiki: Access Control Lists: https://wiki.archlinux.org/title/Access_Control_Lists
