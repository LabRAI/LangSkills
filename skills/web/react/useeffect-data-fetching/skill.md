# React useEffect：数据请求与清理（避免竞态/泄漏）

## Goal
- 用 `useEffect` 正确处理“依赖变化→发起请求→清理/取消→更新 UI”的最小闭环，避免竞态与内存泄漏类问题。

## When to use
- 需要把组件状态与外部系统同步（网络请求、订阅、定时器、DOM API）
- 需要在输入变化时重新拉取数据，并确保旧请求不会覆盖新结果

## When NOT to use
- 只是把已有 `props/state` 计算出一个值（应直接计算或用 `useMemo`）
- 你希望“只执行一次”但没有做好 Strict Mode 下的幂等与 cleanup（先改造为可重复执行）

## Prerequisites
- Environment: 现代浏览器或 React 运行环境（Vite/Next.js 等）
- Permissions: 可访问目标 API（同源或已处理 CORS/鉴权）
- Tools: React（hooks）
- Inputs needed: 触发请求的输入（如 `userId`）、请求 URL/参数、错误与 loading 的 UI 约定

## Steps (<= 12)
1. 先判断是否真的需要 effect：只有当你在同步“外部系统”（网络/订阅/计时器等）时才用 `useEffect`；避免在 effect 里派生 state。[[3]]
2. 明确 effect 的依赖：把 effect 使用到的 `props/state` 放进依赖数组，避免 stale 读取；必要时用 `useCallback`/`useMemo` 稳定依赖。[[1][2]]
3. 设计三态 UI：至少区分 `loading`/`data`/`error`，并在开始请求时重置（避免 UI 继续显示旧数据）。[[2]]
4. 为请求加“取消/过期保护”：用 `AbortController` + `signal`（或“忽略旧响应”的 flag），在 cleanup 中终止/标记过期，避免竞态更新。[[2]]
5. 把“请求函数”放在 effect 内（或由稳定依赖注入），避免每次 render 生成新函数导致不必要的重复请求。[[1][2]]
6. 处理 Strict Mode：开发环境可能额外执行一次 effect 用于发现副作用；确保 effect 幂等、cleanup 完整，不依赖“只跑一次”。[[2]]
7. 不要为了“少写依赖”而禁用规则：这通常会引入隐蔽 bug；用重构（拆分组件/提取 stable 依赖）来达成目标。[[1][2]]
8. 验收：快速切换输入（如 `userId`），确认旧请求不会覆盖新结果，且卸载组件后不会出现 setState 相关告警。[[2]]

## Verification
- 快速切换输入参数（例如连续切换 3 次 `userId`），最终 UI 只显示最后一次请求结果
- 开发环境（Strict Mode）下不会出现重复订阅/重复请求导致的异常状态
- 网络断开/超时/500 时，UI 能进入 `error` 状态且不会卡死在 `loading`

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 无直接不可逆操作；但错误的依赖/cleanup 可能导致重复请求、超量调用或写入错误数据
- Privacy/credential handling: 不要把 token/PII 写进前端代码或日志；避免在错误信息里输出敏感请求参数
- Confirmation requirement: 先在测试环境对慢网/断网/快速切换做回归，再接入真实 API 与鉴权

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] React reference: useEffect: https://react.dev/reference/react/useEffect
- [2] React Learn: Synchronizing with Effects: https://react.dev/learn/synchronizing-with-effects
- [3] React Learn: You Might Not Need an Effect: https://react.dev/learn/you-might-not-need-an-effect
