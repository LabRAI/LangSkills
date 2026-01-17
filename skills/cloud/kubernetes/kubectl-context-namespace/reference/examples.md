# Examples

## 进入生产前的最小检查
1) `kubectl config current-context`（确认不是 dev）
2) `kubectl cluster-info`（确认 API server）
3) `kubectl --context <prod> -n <ns> get deploy`（只读确认目标）

## 临时查看某个 namespace（不改默认）
- `kubectl --context <context> -n <ns> get pods`
