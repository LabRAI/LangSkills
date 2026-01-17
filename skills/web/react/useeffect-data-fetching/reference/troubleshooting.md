# Troubleshooting

## 无限重复请求/无限渲染
- 症状：输入没变但持续重新请求
- 检查：依赖数组里是否包含每次 render 都会新建的对象/函数（例如内联 `{}`、`() => {}`）
- 处理：把对象/函数移出 render，或用 `useMemo`/`useCallback` 稳定依赖

## 旧请求覆盖新结果（竞态）
- 症状：快速切换 `userId` 后，UI 显示了旧用户数据
- 处理：在 cleanup 中 `abort()`，并在 catch 中忽略 aborted；或使用“忽略旧响应”的标记位

## 卸载后仍 setState
- 症状：控制台出现 setState on unmounted / memory leak 类告警
- 处理：确保 effect cleanup 会终止请求/订阅，并在异步回调里检查是否已取消
