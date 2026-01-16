# Library

## Copy-paste commands

```bash
# Inspect devices and filesystems
lsblk -f

# Mount read-only first
sudo mkdir -p /mnt/data
sudo mount -o ro /dev/sdb1 /mnt/data

# Unmount when done
sudo umount /mnt/data
```

## Prompt snippet

```text
You are a Linux assistant. Provide a safe mount/umount procedure for a device.
Rules:
- Always include an inspection step (lsblk -f) and a read-only mount first.
- Include a verification step and an unmount step.
```
