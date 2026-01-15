# Examples

```bash
# Extract while stripping top-level directory
mkdir -p ./out
tar -tf bundle.tar.gz | head
tar -xzf bundle.tar.gz -C ./out --strip-components=1
```

## Verification transcript (2026-01-15)

```bash
tmp=$(mktemp -d /tmp/skill-verify-tar.XXXXXX)
mkdir -p "$tmp/src"
printf 'hello\n' > "$tmp/src/hello.txt"
printf 'nested\n' > "$tmp/src/nested.txt"

tar -czf "$tmp/src.tar.gz" -C "$tmp/src" .
tar -tzf "$tmp/src.tar.gz" | sort

mkdir -p "$tmp/out"
tar -xzf "$tmp/src.tar.gz" -C "$tmp/out"
diff -u "$tmp/src/hello.txt" "$tmp/out/hello.txt"
```

Output (sample; `diff` is empty when files are identical):

```text
./
./hello.txt
./nested.txt
```
