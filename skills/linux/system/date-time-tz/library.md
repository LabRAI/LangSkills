# Library

## Copy-paste commands

```bash
# ISO timestamp
date -Iseconds

# UTC time
date -u

# Time in a specific timezone (one-off)
TZ=UTC date -Iseconds
```

## Prompt snippet

```text
You are a Linux assistant. Help the user format timestamps with date.
Rules:
- Prefer ISO-8601 for logs.
- Explain UTC vs local clearly.
```
