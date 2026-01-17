# Library

## Copy-paste commands（只读优先）

```bash
# 1) Show current context
kubectl config current-context

# 2) List contexts
kubectl config get-contexts

# 3) Switch context
kubectl config use-context <context>

# 4) Verify cluster identity
kubectl cluster-info

# 5) Set default namespace for current context
kubectl config set-context --current --namespace=<ns>

# 6) Always be explicit for safety
kubectl --context <context> -n <ns> get pods
```

## Prompt snippet

```text
You are a Kubernetes operator. Write a safe checklist to avoid running kubectl commands in the wrong cluster/namespace.
Constraints:
- Steps <= 12 with a verification step.
- Prefer read-only checks before any write operation.
```
