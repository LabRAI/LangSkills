# Examples

```bash
find . -type f -newer ./reference.txt -print
```

## Verification transcript (2026-01-15)

```bash
tmp=$(mktemp -d /tmp/skill-verify-find.XXXXXX)
mkdir -p "$tmp/sub"
echo 'hello' > "$tmp/a.log"
echo 'world' > "$tmp/b.txt"
echo 'sub' > "$tmp/sub/c.log"

echo "# find *.log"
find "$tmp" -type f -name '*.log' -print | sort

echo "# find maxdepth=1 *.log"
find "$tmp" -maxdepth 1 -type f -name '*.log' -print | sort
```

Output (sample):

```text
# find *.log
/tmp/skill-verify-find.13PN5Z/a.log
/tmp/skill-verify-find.13PN5Z/sub/c.log
# find maxdepth=1 *.log
/tmp/skill-verify-find.13PN5Z/a.log
```
