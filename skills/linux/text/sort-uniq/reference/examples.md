# Examples

```bash
# Unique by the first column (CSV-like, simple case)
sort -t',' -k1,1 data.csv | uniq
```

## Verification transcript (2026-01-15)

```bash
tmp=$(mktemp -d /tmp/skill-verify-sort.XXXXXX)
cat > "$tmp/in.txt" <<'EOF'
b
a
b
c
a
EOF

echo "# sort"
sort "$tmp/in.txt"

echo "# uniq -c"
sort "$tmp/in.txt" | uniq -c
```

Output (sample):

```text
# sort
a
a
b
b
c
# uniq -c
   2 a
   2 b
   1 c
```
