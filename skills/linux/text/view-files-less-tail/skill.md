# 查看文件与日志：less/head/tail -f 的实战用法

## Goal
- 用 `less`/`head`/`tail` 高效查看文件与日志（避免 `cat` 大文件），并用 `tail -F` 跟随滚动日志。

## When to use
- 快速查看配置/输出的开头或结尾
- 排查服务日志并实时跟随新输出
- 需要在超大文件中查找/跳转（用 less 分页）

## When NOT to use
- 需要结构化分析/聚合统计（用 `awk`/`jq`/日志平台）
- 文件包含敏感信息且你要把内容截图/粘贴到公开渠道

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件可读
- Tools: `less` / `head` / `tail`
- Inputs needed: 目标文件路径（日志/配置/输出）

## Steps (<= 12)
1. 分页查看：`less -N <file>`（`/pattern` 搜索，`n/N` 跳下/上一个）[[1]]
2. 只看开头：`head -n 50 <file>`；或在 less 中直接 `g/G` 跳到开头/末尾[[1][3]]
3. 只看末尾：`tail -n 200 <file>`[[2]]
4. 实时跟随：`tail -f <log>`（滚动输出）[[2]]
5. 处理日志轮转：用 `tail -F <log>`（文件被替换/重建时更稳）[[2]]

## Verification
- `tail -f/-F` 能看到新写入的日志行
- `less` 中搜索能定位到期望关键字并能来回跳转

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读操作）
- Privacy/credential handling: 日志/配置可能包含 token/密钥/用户数据；分享前脱敏
- Confirmation requirement: 无

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Arch man: less(1): https://man.archlinux.org/man/less.1.en.txt
- [2] Arch man: tail(1): https://man.archlinux.org/man/tail.1.en.txt
- [3] Arch man: head(1): https://man.archlinux.org/man/head.1.en.txt
