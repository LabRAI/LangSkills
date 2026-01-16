# Library

## Copy-paste commands

```bash
# Change owner and group for a single path
sudo chown app:app ./data

# Change group only (common for shared folders)
sudo chgrp developers ./shared

# Recursive change (be careful)
sudo chown -R app:app ./var/app
```

## Prompt snippet

```text
Given a target path and desired owner/group, produce a safe chown/chgrp plan.
Rules: include a pre-check step, avoid unsafe recursion, and include verification.
```
