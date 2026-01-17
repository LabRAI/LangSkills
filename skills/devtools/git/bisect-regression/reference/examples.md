# Examples

## 最小化定位
- good：上周发布 tag
- bad：当前 main
- 测试：`npm test`（或单测子集）

## 自动化定位（CI 友好）
- 把“判定脚本”写成退出码规范（0=good, 1=bad）
- 记录 bisect 输出的首个坏提交并附上日志
