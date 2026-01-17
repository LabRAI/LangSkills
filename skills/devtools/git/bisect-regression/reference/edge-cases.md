# Edge cases

- 大量 merge：bisect 仍可用，但可能需要对 merge commit 的结果更谨慎解读
- 需要外部服务：测试依赖数据库/网络时，结果易波动；优先用 mock/fixture
- flaky tests：会导致定位结果不可信；先修复 flaky 或把判定降级为更粗粒度信号
