# 磁盘空间排查：df/du 找出占用最大的目录与文件

## Goal
- 用 `df` 快速判断哪个文件系统快满，用 `du` 定位具体目录（必要时缩小到 Top N）。

## When to use
- 磁盘告警/写入失败（No space left）
- 需要找出占用最大的目录用于清理或迁移

## When NOT to use
- 你需要精确到“哪个进程占用已删除文件”（先用 `lsof`）
- 对生产环境做大范围 du 扫描会造成 IO 压力（选择低峰期）

## Prerequisites
- Environment: Linux shell
- Permissions: 读取目录（扫描系统目录通常需要 sudo）
- Tools: `df` / `du` / `sort` / `tail`
- Inputs needed: 要排查的挂载点或目录路径

## Steps (<= 12)
1. 先看全局：`df -hT`（关注 Use% 与文件系统类型）[[1][3]]
2. 排除虚拟 FS：`df -hT -x tmpfs -x devtmpfs`（更聚焦真实磁盘）[[1][3]]
3. 在目标目录找大户：`du -xh --max-depth=1 <dir> | sort -h`[[2]]
4. 取 Top N：`du -xh --max-depth=1 <dir> | sort -h | tail -n 20`[[2]]
5. 看单目录总量：`du -sh <dir>`（用于快速对比前后）[[2]]
6. 清理/迁移后复查：再次 `df -hT` 对比 Use% 变化[[1][3]]

## Verification
- `df` Use% 下降符合预期
- 对已清理目录 `du -sh` 与清理前对比

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 清理/删除数据可能不可逆；先备份/确认保留策略
- Privacy/credential handling: `du`/路径清单可能泄露业务结构；分享前脱敏
- Confirmation requirement: 先用 du 列出 Top N，逐项确认再删；避免在根目录全量扫描

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU coreutils manual: df invocation: https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html
- [2] GNU coreutils manual: du invocation: https://www.gnu.org/software/coreutils/manual/html_node/du-invocation.html
- [3] Arch man: df(1): https://man.archlinux.org/man/df.1.en.txt
