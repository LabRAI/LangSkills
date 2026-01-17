# Edge cases

- 私有仓库：需要确保 token 对该仓库有访问权限（细粒度 token 的 repository selection）
- 组织策略：组织可能限制 PAT 使用或要求 SSO 授权
- rate limit：高频写入需要队列化与退避，不要紧循环重试
