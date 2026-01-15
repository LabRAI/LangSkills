# Edge cases

- 服务器可能禁用 root 登录或只允许特定 key 选项；需要管理员策略配合。
- 多 key 场景建议为不同用途创建不同 key，并在 authorized_keys 配置限制（command/from 等）。
