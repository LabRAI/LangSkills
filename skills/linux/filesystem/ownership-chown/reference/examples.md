# Examples

```bash
# Preview a service directory, then fix ownership
ls -ld /var/lib/myservice /var/lib/myservice/* | head
sudo chown -R myservice:myservice /var/lib/myservice
```
