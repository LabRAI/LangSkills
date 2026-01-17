# GitHub REST API：用 curl 创建 issue（安全存储 token）

## Goal
- 用 GitHub REST API 创建 issue（自动化工单/告警/周报），并保证 token 最小权限、不会泄露到日志或仓库。

## When to use
- 需要从脚本/CI/服务端把事件写入 GitHub issue（例如异常告警、数据审计发现、例行任务）
- 你希望先用 curl 验证最小可行，再接入 SDK/服务化

## When NOT to use
- 你需要复杂的交互与批量写入（更适合用专门的集成服务或 SDK + 重试/幂等）
- 你无法安全保管 token（先补齐 secret 管理与访问控制）

## Prerequisites
- Environment: 能访问 `api.github.com` 的环境
- Permissions: 对目标仓库有创建 issue 权限
- Tools: `curl`（或任意 HTTP 客户端）
- Inputs needed: `owner/repo`、issue 标题/正文、鉴权 token 的安全存储方式

## Steps (<= 12)
1. 准备最小权限的 token（按需要选择 PAT/细粒度 token），并存入密钥管理或环境变量，不要写进仓库。[[2]]
2. 确认目标仓库与创建权限：`owner/repo` 必须正确，且 token 能访问该仓库。[[2]]
3. 构造创建 issue 的请求：对 `POST /repos/{owner}/{repo}/issues` 提供 `title`（可选 `body/labels/assignees`）。[[1]]
4. 用 curl 发送请求（示例）：`curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" -H \"Accept: application/vnd.github+json\" https://api.github.com/repos/<owner>/<repo>/issues -d '{\"title\":\"...\"}'`[[1][2]]
5. 处理失败：检查 HTTP 状态码与响应体；对 401/403 优先排查 token 权限与仓库可见性。[[2]]
6. 考虑速率限制：对 403/429 场景读取 rate limit 相关响应头，并做退避重试。[[3]]
7. 做幂等：为自动化创建 issue 加上去重键（例如标题包含 run-id），避免重试导致重复创建。[[1]]
8. 验收：在 GitHub 页面确认 issue 已创建且字段正确；同时确认日志中没有泄露 token。[[2]]

## Verification
- issue 在目标仓库中可见，标题/正文/标签符合预期
- 失败场景（权限不足/速率限制）能在日志中定位原因
- 任意日志/输出中不包含 token 明文

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 创建 issue 会写入仓库历史；自动化重试可能造成重复 issue（需幂等）
- Privacy/credential handling: token 属于高敏感凭证；禁止打印、禁止提交；及时轮转与最小权限
- Confirmation requirement: 先在测试仓库验证，再对生产仓库启用；上线前做一次日志脱敏检查

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] GitHub docs: REST API - Create an issue: https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#create-an-issue
- [2] GitHub docs: Managing your personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- [3] GitHub docs: Rate limits for the REST API: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
