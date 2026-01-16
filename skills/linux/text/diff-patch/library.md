# Library

## Copy-paste commands

```bash
# Create a unified diff patch
diff -u old.txt new.txt > change.patch

# Dry-run apply first
patch --dry-run -p0 < change.patch

# Apply and (if needed) revert
patch -p0 < change.patch
patch -R -p0 < change.patch
```

## Prompt snippet

```text
You are a Linux assistant. Help the user create and apply a patch safely.
Rules:
- Always include a dry-run patch step.
- Explain -pN briefly if paths don't match.
```
