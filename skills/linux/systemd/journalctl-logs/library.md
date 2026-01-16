# Library

## Copy-paste commands

```bash
sudo journalctl -u nginx --since '2 hours ago' --no-pager | tail -n 200
sudo journalctl -u nginx -f
sudo journalctl -p warning..err -u nginx --since today --no-pager
```

## Prompt snippet

```text
Given a failing systemd service, output the best journalctl commands to get recent errors, follow live logs, and narrow by time/priority.
```
