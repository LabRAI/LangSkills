# git bisect：自动定位引入回归的提交（可回放/可复现）

## Goal
- 用 `git bisect` 在“已知 good commit”和“已知 bad commit”之间二分定位首个引入回归的提交，并保留可复现的判定依据（测试命令）。

## When to use
- 你能明确“某个版本正常、某个版本异常”，且可以用测试/脚本判断好坏
- 需要把回归定位过程自动化（`git bisect run`）以节省人工试错

## When NOT to use
- 你无法定义稳定的“好/坏”判定（先补齐最小可复现测试）
- 仓库历史不连贯（大量 merge、不可编译区间）导致每一步都需要手工修复（先缩小区间或换策略）

## Prerequisites
- Environment: 本地 git 工作区
- Permissions: 能 checkout 历史提交并运行测试
- Tools: `git`
- Inputs needed: 一个 good commit（已知正常）、一个 bad commit（已知异常）、一条可自动化运行的测试命令

## Steps (<= 12)
1. 准备好坏边界：选一个已知正常的 `good` 与已知异常的 `bad`（最好能用同一条测试命令判定）。[[1]]
2. 开始 bisect：`git bisect start`[[1]]
3. 标记坏提交：`git bisect bad <bad>`（或当前 HEAD 就坏则 `git bisect bad`）。[[1]]
4. 标记好提交：`git bisect good <good>`。[[1]]
5. 对 bisect checkout 出来的提交运行测试，按结果标记：通过则 `git bisect good`，失败则 `git bisect bad`。[[1]]
6. 如果判定能脚本化，用 `git bisect run <cmd>` 自动循环（确保命令对退出码有明确约定）。[[1][2]]
7. 找到首个坏提交后，记录输出的 commit hash、作者、commit message，并把复现步骤写进 issue/PR。[[1]]
8. 结束并回到原分支：`git bisect reset`。[[1]]

## Verification
- 复现：在“首个坏提交”上运行同一测试命令，稳定失败
- 回归：在紧邻的前一个提交上运行同一测试命令，稳定通过
- 记录：issue/PR 中包含命令、环境、好坏边界 commit，便于他人复核

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: `bisect` 本身不改历史；但测试脚本可能会修改工作区/生成文件，建议在干净工作区运行
- Privacy/credential handling: 不要在 bisect 测试脚本里打印密钥/生产配置；避免把私有路径写进公开日志
- Confirmation requirement: 先用手工 1-2 次 `good/bad` 验证判定标准可靠，再启用 `git bisect run`

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] git docs: git-bisect: https://git-scm.com/docs/git-bisect
- [2] git docs mirror: git-bisect (kernel.org): https://www.kernel.org/pub/software/scm/git/docs/git-bisect.html
- [3] git docs mirror: git-bisect (mirrors.edge.kernel.org): https://mirrors.edge.kernel.org/pub/software/scm/git/docs/git-bisect.html
