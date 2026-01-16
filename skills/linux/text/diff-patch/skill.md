# 对比与打补丁：diff/patch 的安全用法（含 dry-run）

## Goal
- 用 diff 生成统一补丁，用 patch 以 dry-run 方式安全应用，并能在出错时回滚。

## When to use
- 需要对比两个文件/目录的差异并形成可应用的补丁
- 在没有 git 的环境中应用变更（或对第三方补丁做审阅）

## When NOT to use
- 仓库已有 git 且可以直接开分支/PR（优先用 git 的 diff/apply/checkout）
- 你不理解补丁影响范围（先做 dry-run 与备份）

## Prerequisites
- Environment: Linux shell
- Permissions: 对目标文件有写权限（应用 patch）
- Tools: `diff`, `patch`
- Inputs needed: 原文件/新文件路径；补丁要应用到的工作目录

## Steps (<= 12)
1. 生成统一 diff：`diff -u old.txt new.txt > change.patch`[[1][2]]
2. 审阅补丁内容：`sed -n '1,120p' change.patch`（确认没有误改路径/大段无关变更）[[1]]
3. 应用前先 dry-run：`patch --dry-run -p0 < change.patch`（应提示成功或给出冲突点）[[3]]
4. dry-run 通过后再应用：`patch -p0 < change.patch`[[3]]
5. 验证应用结果：`diff -u old.txt new.txt` 应为空（或按预期变化）[[1][2]]
6. 需要回滚时：`patch -R -p0 < change.patch`（反向应用）[[3]]

## Verification
- `patch --dry-run` 通过；应用后目标文件内容符合预期
- 如是文本文件，可用 `diff -u` 再对比确认

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: patch 会修改文件；在没有版本控制时风险更高
- Privacy/credential handling: 补丁可能包含敏感路径/内容；共享前检查并脱敏
- Confirmation requirement: 始终先 `--dry-run`；对关键文件先备份或在 git 分支上操作

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] man7 diff(1): https://man7.org/linux/man-pages/man1/diff.1.html
- [2] GNU diffutils manual: https://www.gnu.org/software/diffutils/manual/diffutils.html
- [3] man7 patch(1): https://man7.org/linux/man-pages/man1/patch.1.html
