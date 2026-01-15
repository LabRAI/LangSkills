# Examples

```bash
# Extract while stripping top-level directory
mkdir -p ./out
tar -tf bundle.tar.gz | head
tar -xzf bundle.tar.gz -C ./out --strip-components=1
```
