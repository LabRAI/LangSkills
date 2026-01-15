# 安全删除文件：rm 的正确姿势与先预览后删除

## Goal
- 安全删除文件/目录：先预览，再确认，再执行（避免误删）。

## When to use
- 清理临时文件/构建产物
- 需要批量删除但希望可审阅清单

## When NOT to use
- 不确定匹配范围（先 `find ... -print`）
- 涉及生产/关键数据（先备份/走审批）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标路径有删除权限（可能需要 sudo）
- Tools: `rm`（可选 `find`）
- Inputs needed: 目标路径/匹配模式

## Steps (<= 12)
1. 先 dry-run 列出将删除目标：`ls -la -- <path>` 或 `find ... -print`[[1][3]]
2. 单个/少量目标：用交互确认 `rm -i -- <path>`[[1][3]]
3. 大量目标：用 `rm -I`（一次性确认）而不是无脑 `-f`[[1][3]]
4. 目录删除更谨慎：`rm -rI -- <dir>`；批量用 find 两阶段：先 print，再 `-exec rm -i`[[1][2][3]]

## Verification
- 确认目标不存在：`test ! -e <path> && echo ok`
- 如果在 git 仓库：`git status` 确认没有误删

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 删除通常不可逆（尤其绕过回收站时）
- Privacy/credential handling: 删除清单/路径可能包含敏感信息，分享前脱敏
- Confirmation requirement: 任何批量删除必须先 dry-run 输出清单并人工审阅；避免使用 `rm -rf`

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU coreutils manual: rm invocation: https://www.gnu.org/software/coreutils/manual/html_node/rm-invocation.html
- [2] POSIX rm specification: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/rm.html
- [3] Arch man: rm(1): https://man.archlinux.org/man/rm.1.en.txt
