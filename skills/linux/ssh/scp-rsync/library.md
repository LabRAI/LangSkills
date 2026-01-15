# Library

## Copy-paste commands

```bash
scp ./file.txt user@host:/tmp/
scp -r ./dir user@host:/tmp/
rsync -avP --dry-run -e ssh ./dir/ user@host:/tmp/dir/
rsync -avP -e ssh ./dir/ user@host:/tmp/dir/
```

## Prompt snippet

```text
Given src and dest paths, choose scp or rsync, then output safe commands including dry-run and verification. Warn about --delete and trailing slashes.
```
