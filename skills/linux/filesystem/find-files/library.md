# Library

## Copy-paste commands

```bash
# 1) Find files by name (dry-run print only)
find . -type f -name '*.log' -print

# 2) Find directories by name
find . -type d -name 'node_modules' -print

# 3) Find files modified in last 7 days
find /var/log -type f -mtime -7 -print

# 4) Find big files (>100MB) (may produce permission errors)
find / -type f -size +100M -print 2>/dev/null
```

## Prompt snippet

```text
You are a Linux assistant. Write a safe, minimal find(1) command.
Inputs: root directory, filter conditions (name/type/time/size), and whether the output is for read-only listing or a write operation.
Rules:
- Always provide a dry-run print-only command first.
- Steps <= 12, include a verification step.
```
