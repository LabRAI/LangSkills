# Library

## Copy-paste commands

```bash
chmod u+x ./script.sh
chmod 644 ./file.txt
chmod 755 ./dir
find ./dir -type d -exec chmod 755 {} +
find ./dir -type f -exec chmod 644 {} +
```

## Prompt snippet

```text
Given a path and desired access, produce a minimal chmod plan with verification and safety notes.
```
