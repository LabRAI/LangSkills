# Examples

```bash
# TSV: extract first three fields
cut -f1-3 data.tsv | head
```

## Verification transcript (2026-01-15)

```bash
tmp=$(mktemp -d /tmp/skill-verify-cut.XXXXXX)
cat > "$tmp/data.csv" <<'EOF'
name,age,city
alice,30,nyc
bob,25,bos
EOF

printf 'a\nb\n' > "$tmp/col1.txt"
printf '1\n2\n' > "$tmp/col2.txt"

echo "# cut col1+col3"
cut -d',' -f1,3 "$tmp/data.csv"

echo "# paste"
paste -d',' "$tmp/col1.txt" "$tmp/col2.txt"
```

Output (sample):

```text
# cut col1+col3
name,city
alice,nyc
bob,bos
# paste
a,1
b,2
```
