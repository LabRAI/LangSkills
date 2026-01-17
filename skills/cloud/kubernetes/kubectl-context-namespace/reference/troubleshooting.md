# Troubleshooting

## 找不到 context / current-context 未设置
- 检查：`kubectl config get-contexts` 是否为空
- 处理：确认 `KUBECONFIG` 环境变量/默认路径是否正确；从平台团队获取 kubeconfig

## 权限不足（Forbidden）
- 检查：`kubectl auth can-i get pods -n <ns>`
- 处理：申请最小权限（只读→再逐步增加），避免使用 cluster-admin 账号

## namespace 不存在
- 检查：`kubectl get namespaces | rg -n '^<ns>\\b'`
- 处理：切换到正确环境，或让对应团队创建/授权目标 namespace
