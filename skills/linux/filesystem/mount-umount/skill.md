# 挂载与卸载：mount/umount 的安全流程（含常见故障）

## Goal
- 按安全流程挂载/卸载文件系统：先确认设备，再只读验证，再按需读写挂载，最后安全卸载。

## When to use
- 需要临时挂载磁盘/分区/镜像查看内容
- 需要挂载移动硬盘或云盘以读写文件

## When NOT to use
- 不确定设备节点（/dev/xxx）指向什么（先停下，避免挂错盘）
- 生产环境在线挂载/卸载且不清楚影响范围（先评估依赖与回滚）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常需要 root 权限（`sudo`）进行 mount/umount
- Tools: `lsblk`, `mount`, `umount`
- Inputs needed: 设备节点（例如 /dev/sdb1）与挂载点目录（例如 /mnt/data）

## Steps (<= 12)
1. 确认设备与文件系统：`lsblk -f`（核对 SIZE/UUID/FSTYPE，避免挂错盘）[[1]]
2. 创建挂载点目录：`sudo mkdir -p /mnt/data`[[2]]
3. 先用只读挂载做验证：`sudo mount -o ro <device> /mnt/data`[[2]]
4. 验证挂载成功：`mount | grep /mnt/data` 并查看可用空间：`df -h /mnt/data`[[2]]
5. 需要读写时，先卸载只读再重新挂载：`sudo umount /mnt/data && sudo mount <device> /mnt/data`[[2][3]]
6. 完成后安全卸载：`sudo umount /mnt/data`（提示 busy 时先停止占用进程，再重试）[[3]]

## Verification
- `mount | grep <mountpoint>` 能看到挂载记录；卸载后记录消失
- `df -h <mountpoint>` 能显示该挂载点的空间信息

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 挂载到错误的设备/分区可能导致误操作；读写挂载下的删除/覆盖是不可逆的
- Privacy/credential handling: 挂载介质可能包含敏感数据；确认访问权限与共享策略
- Confirmation requirement: 任何读写操作前先只读挂载检查；在生产环境先确认依赖与回滚路径

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: lsblk(8): https://man.archlinux.org/man/lsblk.8.en.txt
- [2] Arch man: mount(8): https://man.archlinux.org/man/mount.8.en.txt
- [3] Arch man: umount(8): https://man.archlinux.org/man/umount.8.en.txt
