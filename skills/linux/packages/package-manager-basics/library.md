# Library

## Copy-paste commands

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install curl

# Fedora/RHEL
sudo dnf makecache
sudo dnf install curl

# Arch
sudo pacman -Syu
sudo pacman -S curl
```

## Prompt snippet

```text
Given a distro family and a desired package action, output safe package-manager commands with a preview/verification step and rollback notes.
```
