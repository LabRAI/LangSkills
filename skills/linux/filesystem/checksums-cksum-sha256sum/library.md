# Library

## Copy-paste commands

```bash
# Generate checksum file
sha256sum ./artifact.bin > artifact.bin.sha256

# Verify checksum file
sha256sum -c artifact.bin.sha256

# Portable checksum (CRC + bytes)
cksum ./artifact.bin
```

## Prompt snippet

```text
You are a Linux assistant. Help the user verify file integrity using checksums.
Rules:
- Prefer sha256sum for modern workflows; mention cksum for POSIX portability.
- Include a verification command and what success looks like.
```
