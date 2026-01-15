# Library

## Copy-paste commands

```bash
# Temporarily set an env var for one command
HTTP_PROXY=http://127.0.0.1:7890 curl -I https://example.com

# Append to PATH (current shell only)
export PATH="$PATH:/opt/bin"
command -v mytool
```

## Prompt snippet

```text
You are a Linux assistant. Help the user fix an environment variable or PATH issue safely.
Rules:
- Prefer temporary changes first, then explain how to persist.
- Warn about leaking secrets when printing env.
```
