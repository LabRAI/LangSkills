# Library

## Copy-paste commands

```bash
sudo systemctl status nginx
sudo systemctl restart nginx
sudo systemctl enable --now nginx
sudo systemctl cat nginx
sudo systemctl --failed
```

## Prompt snippet

```text
Given a systemd service issue, output a safe systemctl workflow: status -> (reload/restart) -> enable/disable -> verify. Include risk notes.
```
