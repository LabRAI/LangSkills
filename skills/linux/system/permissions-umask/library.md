# Library

## Copy-paste commands

```bash
# Check current umask
umask

# Set a stricter default (current shell only)
umask 077
rm -f t && touch t && stat -c '%a %n' t
```

## Prompt snippet

```text
You are a Linux assistant. Help the user choose and verify a safe umask value.
Rules:
- Explain the 666/777 baseline and how umask masks bits.
- Include a verification step with touch+stat.
```
