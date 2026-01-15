# Examples

```bash
# Patch a whole directory tree (review carefully)
diff -ruN old_dir new_dir > dir.patch
patch --dry-run -p0 < dir.patch
```

## Verification transcript (2026-01-15)

```bash
tmp=$(mktemp -d /tmp/skill-verify-patch.XXXXXX)
cat > "$tmp/old.txt" <<'EOF'
line1
line2
EOF
cat > "$tmp/new.txt" <<'EOF'
line1
line2 changed
line3
EOF

cd "$tmp"
diff -u old.txt new.txt > change.patch || true

echo "# patch --dry-run"
patch --dry-run < change.patch

echo "# patch apply"
patch < change.patch

echo "# diff after (should be empty)"
diff -u old.txt new.txt || true
```

Output (sample):

```text
# patch --dry-run
patching file old.txt
# patch apply
patching file old.txt
# diff after (should be empty)
```
