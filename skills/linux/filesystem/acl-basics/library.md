# Library

## Copy-paste commands

```bash
# Inspect ACL
getfacl -p ./shared

# Allow alice to read/write
sudo setfacl -m u:alice:rw ./shared/file.txt

# Default ACL on directory (new files inherit)
sudo setfacl -d -m u:alice:rwx ./shared

# Remove alice entry / remove all ACL
sudo setfacl -x u:alice ./shared/file.txt
sudo setfacl -b ./shared
```

## Prompt snippet

```text
Explain ACL vs chmod, then give a minimal setfacl plan to grant a user access to a directory.
Include verification with sudo -u and a rollback step.
```
