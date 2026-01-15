# Library

## Copy-paste commands

```bash
find . -type f -name '*.tmp' -print
rm -i -- ./some-file.tmp
rm -rI -- ./build/
find . -type f -name '*.tmp' -exec rm -i {} +
```

## Prompt snippet

```text
Write a safe deletion plan for Linux.
Always provide a dry-run listing first; avoid rm -rf; require confirmation for recursive operations.
```
