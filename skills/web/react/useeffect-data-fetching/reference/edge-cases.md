# Edge cases

- 开发环境 Strict Mode：effect 可能被额外执行一次以发现副作用（要求幂等与完整 cleanup）
- 慢网/超时：loading 状态可能持续很久，UI 需要可取消或可重试
- 快速切换输入：需要防竞态（旧响应不应覆盖新状态）
