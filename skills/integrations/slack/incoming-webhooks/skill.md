# Slack Incoming Webhooks：安全发送消息（无需 bot token）

## Goal
- 用 Incoming Webhooks 安全地向 Slack channel 发送消息，并避免凭证泄露与误发。

## When to use
- 需要从脚本/CI/服务端快速发送通知到 Slack
- 不需要用户交互，也不想引入完整的 bot token 流程

## When NOT to use
- 需要以用户身份操作或读取数据（应使用 OAuth + Web API）
- Webhook URL 可能被泄露且你无法及时轮转（先补齐密钥管理）

## Prerequisites
- Environment: 能发起 HTTPS 请求的环境（本地 shell / CI / 后端服务均可）
- Permissions: 有权限在目标 Slack workspace 安装/配置 app 或创建 webhook
- Tools: `curl`（可选，用于快速测试）
- Inputs needed: Webhook URL、目标 channel（由 Slack 配置决定）、消息文本或 blocks payload

## Steps (<= 12)
1. 确认消息目标与使用方式：只做通知（webhook）还是需要更复杂能力（Web API/OAuth）。[[2][3]]
2. 在 Slack 中创建/获取 Incoming Webhook，并拿到 webhook URL（不要在聊天/工单里明文传播）。[[1]]
3. 把 webhook URL 存到密钥管理（CI secret / 环境变量），避免写进仓库与日志。[[1][3]]
4. 先做最小化联通测试：`curl -X POST -H 'Content-type: application/json' --data '{"text":"hello"}' "$SLACK_WEBHOOK_URL"`[[1]]
5. 需要富文本时，用 blocks 组装 payload（先在小范围 channel 验证格式与展示）。[[1]]
6. 处理失败与限流：记录 HTTP 状态码；遇到 429/失败时做指数退避重试并告警。[[2]]
7. 对消息做最小必要内容输出：避免把敏感信息（token/PII/内部链接）推送到公共 channel。[[3]]
8. 如果怀疑泄露或滥用，立即轮转 webhook（重新生成并替换 secret），并回收旧 URL。[[1]]

## Verification
- Slack channel 中出现预期消息（文本/blocks 渲染正确）
- 失败场景能在日志中定位（状态码/响应体/重试次数），且不会打印 webhook URL 明文

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 向错误的 channel 发送消息可能造成信息泄露；泄露 webhook URL 可能导致滥发消息
- Privacy/credential handling: 不要把 webhook URL、token、PII 写入 repo/日志/截图；避免在公共 channel 推送敏感内容
- Confirmation requirement: 先在测试/私有 channel 做 dry-run，再切换到生产 channel；上线前做一次泄露风险检查

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] slackapi/node-slack-sdk - @slack/webhook README: https://github.com/slackapi/node-slack-sdk/blob/main/packages/webhook/README.md?plain=1
- [2] slackapi/node-slack-sdk - @slack/web-api README: https://github.com/slackapi/node-slack-sdk/blob/main/packages/web-api/README.md?plain=1
- [3] slackapi/node-slack-sdk - @slack/oauth README: https://github.com/slackapi/node-slack-sdk/blob/main/packages/oauth/README.md?plain=1
