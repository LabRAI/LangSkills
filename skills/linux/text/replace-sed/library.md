# Library

## Copy-paste commands

```bash
# Preview
sed 's/foo/bar/g' ./config.ini | head

# In-place with backup
sed -i.bak 's/foo/bar/g' ./config.ini

# Rollback
mv ./config.ini.bak ./config.ini
```

## Prompt snippet

```text
Given old/new strings and target files, produce a safe sed replacement plan with preview, backup, and verification.
```
