# Examples

```bash
# Backup ACL then change
getfacl -R ./shared > ./shared.acl.backup.txt
sudo setfacl -m u:alice:rwx ./shared
```
