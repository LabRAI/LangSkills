# Examples

- 用户详情：`userId` 变化时重新拉取，并在切换时取消旧请求
- 搜索建议：输入变化频繁，配合 debounce（在 effect cleanup 清理 timer）降低请求频率
- 订阅类外部系统：WebSocket/EventSource 在 cleanup 中关闭连接
