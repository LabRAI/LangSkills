# Troubleshooting

## 4xx / 5xx from Slack
- 确认 webhook URL 是否有效、是否指向正确 workspace/channel。
- 检查 payload 是否为有效 JSON，且 `Content-type: application/json` 已设置。

## 429 rate limited
- 做指数退避重试；在 CI/批量通知场景增加聚合与降噪。
