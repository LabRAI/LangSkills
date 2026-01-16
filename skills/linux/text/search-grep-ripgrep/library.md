# Library

## Copy-paste commands

```bash
rg -n "TODO" .
rg -n "password|token|secret" . --hidden --glob '!node_modules/**'
grep -R -n -C 2 "ERROR" /var/log 2>/dev/null | head
```

## Prompt snippet

```text
Given a pattern and a codebase path, propose a fast rg/grep search plan with context and safe output handling.
```
