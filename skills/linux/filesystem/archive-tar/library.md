# Library

## Copy-paste commands

```bash
# Create an archive (relative paths)
tar -C ./project -czf project.tar.gz .

# Preview
tar -tzf project.tar.gz | head

# Extract to a directory
mkdir -p ./extract && tar -xzf project.tar.gz -C ./extract
```

## Prompt snippet

```text
Write a safe tar create/extract workflow with preview, extraction destination, and verification steps.
```
