# 文本搜索：grep（或 rg）按关键字/正则定位问题

## Goal
- 用 `grep`/`rg` 在代码/日志中快速定位关键字与正则匹配位置（带行号、上下文、过滤规则）。

## When to use
- 排查报错：在仓库中搜索错误码/函数名/配置项
- 在日志中找某段时间窗口的异常关键词
- 需要批量定位某个模式出现在哪些文件

## When NOT to use
- 需要跨仓库/大规模全文检索（考虑专用搜索服务）
- 需要解析结构化日志/JSON（优先用 `jq`）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件可读
- Tools: `grep`（推荐）/`rg`（更快，默认递归并尊重 .gitignore）
- Inputs needed: pattern（关键字/正则） + 搜索路径

## Steps (<= 12)
1. 单文件带行号：`grep -n 'pattern' file`[[1][2]]
2. 递归搜：优先用 `rg 'pattern' <path>`；或 `grep -R -n 'pattern' <path>`[[2][3][4]]
3. 忽略大小写/整词：`grep -niw 'pattern' ...`；rg 用 `-i -w`[[1][2][4]]
4. 正则 vs 纯文本：`grep -E 're'`（正则）/ `grep -F 'literal'`（不解释正则）[[2]]
5. 上下文：`grep -n -C 3 'pattern' ...`；rg 用 `-C 3`[[2][4]]
6. 过滤文件/目录：rg 用 `--glob '!node_modules/**'`、`--hidden`；必要时先收敛范围再扩大[[3][4]]

## Verification
- 抽样打开匹配文件确认命中是否为真（避免误匹配）
- 加/减过滤条件，确保结果集符合预期范围

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 无（只读操作）
- Privacy/credential handling: 搜索结果可能包含密钥/用户数据；分享前脱敏或只给路径/行号
- Confirmation requirement: 无

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU grep manual: https://www.gnu.org/software/grep/manual/grep.html
- [2] Arch man: grep(1): https://man.archlinux.org/man/grep.1.en.txt
- [3] ripgrep GUIDE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- [4] Arch man: rg(1): https://man.archlinux.org/man/rg.1.en.txt
