# kubectl 上下文与 namespace：避免在错误集群执行命令

## Goal
- 管理 kubeconfig 的 context 与默认 namespace，降低“在错误集群/错误命名空间执行命令”的事故风险。

## When to use
- 你同时操作多个集群（dev/staging/prod）或多个 namespace
- 需要把“目标集群/namespace”固化到操作前的检查清单里

## When NOT to use
- 你没有 kubeconfig 访问权限（先让平台团队提供最小权限的 kubeconfig）
- 你无法区分环境（建议先建立命名规范与只读账号）

## Prerequisites
- Environment: 能访问 Kubernetes API 的环境
- Permissions: 有权限读取 kubeconfig 与访问目标集群（至少能 `get` 基本资源）
- Tools: `kubectl`
- Inputs needed: 目标 context 名称、目标 namespace 名称、用于验证的只读命令

## Steps (<= 12)
1. 查看当前 context：`kubectl config current-context`[[1]]
2. 列出所有 context（并观察默认 namespace 列）：`kubectl config get-contexts`[[1]]
3. 切换到目标 context：`kubectl config use-context <context>`[[1]]
4. 用只读信息确认你在对的集群：`kubectl cluster-info`[[2]]
5. 列出 namespace：`kubectl get namespaces`[[3]]
6. 为当前 context 设置默认 namespace：`kubectl config set-context --current --namespace=<ns>`[[1][3]]
7. 对高风险操作保持“显式指定”习惯：`kubectl --context <context> -n <ns> get pods`[[1][2][3]]
8. 验收：只查看当前生效配置片段：`kubectl config view --minify`[[1]]

## Verification
- `kubectl cluster-info` 输出与目标环境一致（API server 地址/命名）
- `kubectl config view --minify` 中的 `context` 与 `namespace` 为预期值
- 使用 `kubectl --context ... -n ... get pods` 能在预期 namespace 返回结果

## Safety & Risk
- Risk level: **medium**
- Irreversible actions: 在错误集群/namespace 执行变更可能造成不可逆影响（删除/滚动更新/扩缩容）
- Privacy/credential handling: kubeconfig 可能包含凭证；不要上传到工单/聊天/日志；使用最小权限账号
- Confirmation requirement: 任何写操作前先跑一条只读校验命令，并显式指定 `--context/-n`

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Kubernetes docs: kubectl Quick Reference: https://kubernetes.io/docs/reference/kubectl/quick-reference/
- [2] Kubernetes docs: kubectl Overview: https://kubernetes.io/docs/reference/kubectl/overview/
- [3] Kubernetes docs: Namespaces: https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/
