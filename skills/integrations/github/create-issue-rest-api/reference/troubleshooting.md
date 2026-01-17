# Troubleshooting

## 401 Unauthorized
- 检查：token 是否正确注入（环境变量/secret）、是否过期/已撤销
- 处理：重新生成并轮转 token；确认请求头使用 `Authorization: Bearer ...`

## 403 Forbidden
- 检查：token 权限是否足够、仓库是否私有、是否触发 rate limit
- 处理：最小权限补齐；若是速率限制则按响应头做退避

## 重复创建 issue
- 处理：在标题/正文加入 run-id；或先搜索已有 issue 再决定创建（幂等）
