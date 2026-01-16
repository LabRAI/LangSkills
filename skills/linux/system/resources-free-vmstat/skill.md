# 资源诊断：free/vmstat/iostat 区分 CPU/内存/IO 瓶颈

## Goal
- 快速区分性能瓶颈来自 CPU、内存还是 IO：用 `free` 看内存，用 `vmstat` 看整体节奏，用 `iostat` 看磁盘。

## When to use
- 机器变慢/延迟升高，需要先做资源层面诊断
- 怀疑 swap 抖动或 IO 等待导致吞吐下降

## When NOT to use
- 你需要进程级别的根因（再结合 `top`/`ps`/`pidstat`）

## Prerequisites
- Environment: Linux shell
- Permissions: 通常无需 sudo（iostat 需要 sysstat 包且可能需要权限读取部分统计）
- Tools: `free` / `vmstat` / `iostat`
- Inputs needed: 采样间隔与次数（例如 1s * 5 次）

## Steps (<= 12)
1. 内存概览：`free -h`（关注 available、swap）[[1]]
2. 节奏采样：`vmstat 1 5`（看 r/b、si/so、wa 等）[[2]]
3. IO 采样：`iostat -xz 1 5`（看 util、await、svctm 等）[[3]]
4. 结合判断：`wa` 高 + iostat await 高 → IO 瓶颈；`si/so` 高 → swap 压力；`r` 高 → CPU 竞争[[2][3]]

## Verification
- 修复/扩容/限流后再次采样，指标改善且业务延迟恢复
- 记录一份“问题时 vs 正常时”的采样对比用于复盘

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读采样）
- Privacy/credential handling: 输出包含主机资源信息；对外分享前确认合规
- Confirmation requirement: 采样本身安全；但不要在高压时运行过重的诊断工具

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: free(1): https://man.archlinux.org/man/free.1.en.txt
- [2] Arch man: vmstat(8): https://man.archlinux.org/man/vmstat.8.en.txt
- [3] Arch man: iostat(1): https://man.archlinux.org/man/iostat.1.en.txt
