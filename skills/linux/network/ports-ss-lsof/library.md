# Library

## Copy-paste commands

```bash
ss -lntup | head
ss -lntup 'sport = :3000'
sudo lsof -i :3000 -sTCP:LISTEN -nP
sudo fuser -n tcp 3000
```

## Prompt snippet

```text
Given a port conflict, propose an ss/lsof workflow to identify the owning process and safely stop or reconfigure it.
```
