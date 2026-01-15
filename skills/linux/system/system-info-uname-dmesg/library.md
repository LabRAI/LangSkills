# Library

## Copy-paste commands

```bash
uname -srmo
lsb_release -a || cat /etc/os-release
dmesg -T | tail -n 200
dmesg -T | grep -i 'error\|fail\|warn' | tail -n 50
```

## Prompt snippet

```text
Given a Linux issue report request, output a minimal uname/lsb_release/dmesg collection checklist with privacy notes.
```
