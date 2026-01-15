# Library

## Copy-paste commands

```bash
sudo useradd -m -s /bin/bash appuser
sudo groupadd developers
sudo usermod -aG developers appuser
id appuser
```

## Prompt snippet

```text
Given a username and required access, output a safe user/group management plan, highlighting sudo/wheel risks and including verification with id.
```
