# Library

## Copy-paste commands

```bash
# Copy without overwriting
cp -n ./src.txt ./dst.txt

# Copy directory and preserve attributes
cp -a ./src_dir ./dst_dir

# Move (rename) without overwriting
mv -n ./old_name ./new_name

# Keep backups when overwriting is possible
cp --backup=numbered ./src.txt ./dst.txt
```

## Prompt snippet

```text
You are a Linux assistant. Write safe cp/mv commands for copying or moving files.
Rules:
- Prefer no-clobber (-n) or interactive (-i) when overwriting is possible.
- If preserving attributes matters, prefer cp -a.
- Include a verification step.
```
