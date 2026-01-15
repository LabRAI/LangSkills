# 批量替换：sed 常见替换、就地修改与备份策略

## Goal
- 用 `sed` 做安全的批量替换：先预览，再就地修改（带备份），最后验证替换结果。

## When to use
- 需要在一批文本文件中替换配置项/URL/路径
- 需要对满足条件的行做局部替换（不想手改）

## When NOT to use
- 需要复杂的多行/结构化编辑（优先用专用工具或脚本）
- 替换风险高且没有备份/回滚方案

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件可读写
- Tools: `sed`（可选 `rg`/`diff` 用于验证）
- Inputs needed: 旧字符串/正则 + 新字符串 + 文件路径/文件集合

## Steps (<= 12)
1. 先预览（不写入）：`sed 's/old/new/g' <file> | head`[[1][2][3]]
2. 限定范围：例如只替换匹配行：`sed '/^key=/s/old/new/' <file>`[[1][2]]
3. 就地修改并备份：`sed -i.bak 's/old/new/g' <file>`（生成 .bak 便于回滚）[[1][3]]
4. 路径替换建议换分隔符：`sed -i.bak 's|/old/path|/new/path|g' <file>`[[1]]
5. 验证：用 `rg old <paths>` 或对比备份 `diff -u <file>.bak <file>`[[1]]

## Verification
- 关键文件 `diff` 符合预期；并且程序/配置可正常加载
- 再次搜索 `old` 确认不再出现（或只在注释/文档中出现）

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 就地修改可能破坏配置/代码；没有备份会难以回滚
- Privacy/credential handling: 替换内容可能包含凭据/内部域名；分享命令时注意脱敏
- Confirmation requirement: 先预览，再带备份执行；对生产配置文件建议先在副本上验证

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GNU sed manual: https://www.gnu.org/software/sed/manual/sed.html
- [2] POSIX sed specification: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/sed.html
- [3] Arch man: sed(1): https://man.archlinux.org/man/sed.1.en.txt
