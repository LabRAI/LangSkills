# Library

## Copy-paste commands

```bash
# Preview first
find . -type f -name '*.log' -print0 | xargs -0 -n 1 echo rm

# Then (only if safe) replace echo with the real command
# find . -type f -name '*.log' -print0 | xargs -0 -n 1 rm -i
```

## Prompt snippet

```text
You are a Linux assistant. Convert a list of items from stdin into a safe xargs pipeline.
Rules:
- Prefer -0 when handling paths, and include a preview step with echo.
- Avoid suggesting irreversible commands without confirmations.
```
