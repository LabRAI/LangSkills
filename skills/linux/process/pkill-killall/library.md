# Library

## Copy-paste commands

```bash
# Preview targets
pgrep -a 'myapp'

# Try graceful termination first
pkill -TERM -f 'myapp'

# Force kill as a last resort (be careful)
# pkill -KILL -f 'myapp'
```

## Prompt snippet

```text
You are a Linux assistant. Help the user stop a process safely.
Rules:
- Always preview targets first (pgrep/ps).
- Prefer TERM, then KILL only if needed.
```
