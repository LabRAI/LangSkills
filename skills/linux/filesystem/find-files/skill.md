# 用 find 精准查找文件与目录（按名称/时间/大小）

## Goal
- 用 `find` 在目录树中按条件查找文件/目录，并安全地输出/统计/进一步处理结果。

## When to use
- 需要按名称、类型、时间、大小等条件筛选文件/目录
- 需要把“匹配到的路径列表”交给后续命令处理（统计/归档/清理等）

## When NOT to use
- 只需要在已知的少量目录里手动定位（`ls`/`tree` 更快）
- 你不确定匹配条件会命中多少文件且后续操作不可逆（先 dry-run 预览）

## Prerequisites
- Environment: Linux shell
- Permissions: 读取目标目录（某些目录可能需要 sudo）
- Tools: `find`
- Inputs needed: 起始目录（root）、匹配条件（name/type/mtime/size）、是否只读或写操作

## Steps (<= 12)
1. 先做 dry-run：`find <root> -type f -name '<pattern>' -print`（只打印不修改）[[1]]
2. 不区分大小写：`find . -type f -iname '*.log' -print`[[1]]
3. 限定对象类型：`-type f|d|l`（例如：`find . -type d -name 'node_modules' -print`）[[1]]
4. 按时间筛选：`-mtime -7` / `-mmin -30`（先 print）[[1]]
5. 按大小筛选：`-size +100M` / `-size -10k`（先 print）[[1]]
6. 限制深度：`-maxdepth N` / `-mindepth N`（避免扫太深）[[1]]
7. 组合条件：`find . \( -name '*.jpg' -o -name '*.png' \) -type f -print`[[1][2]]
8. 写操作优先 `-exec ... {} +`，并要求交互确认：`find . -name '*.tmp' -type f -exec rm -i {} +`[[1][2][3]]

## Verification
- 确认命中数量：`find <root> ... -print | wc -l`
- 抽样检查：把 `-print` 输出重定向到文件后人工审阅（尤其在删除/改权限前）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: `-delete` / `rm` / `-exec` 可能不可逆
- Privacy/credential handling: 避免把敏感路径/文件名复制到公开渠道（日志/截图）
- Confirmation requirement: 任何写操作先 `-print` 预览，再执行；必要时加 `-maxdepth`/更严格条件

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 find(1): https://man7.org/linux/man-pages/man1/find.1.html
- [2] GNU findutils manual (find): https://www.gnu.org/software/findutils/manual/html_mono/find.html
- [3] Arch man: find(1): https://man.archlinux.org/man/find.1.en.txt
