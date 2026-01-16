# Library

## Copy-paste commands

```bash
# gzip compress, keep original
gzip -k ./app.log

# gzip decompress, keep archive
gzip -dk ./app.log.gz

# xz compress (parallel), keep original
xz -k -T0 ./dataset.csv
```

## Prompt snippet

```text
You are a Linux assistant. Provide safe gzip/xz commands for compressing or decompressing files.
Rules:
- Prefer -k to keep originals unless the user explicitly wants replacement.
- Include a verification step.
```
