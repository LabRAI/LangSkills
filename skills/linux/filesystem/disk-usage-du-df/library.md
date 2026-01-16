# Library

## Copy-paste commands

```bash
df -hT
df -hT -x tmpfs -x devtmpfs
sudo du -xh --max-depth=1 /var | sort -h | tail -n 20
du -sh /var/log
```

## Prompt snippet

```text
Given a disk-full incident, produce a safe df/du triage plan.
Include commands to identify the full filesystem, the top directories, and a verification step after cleanup.
```
