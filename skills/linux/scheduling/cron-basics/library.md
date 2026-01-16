# Library

## Copy-paste commands

```bash
crontab -l
crontab -e
# Example line (every 5 minutes):
# */5 * * * * /usr/local/bin/job >>/var/log/job.log 2>&1
```

## Prompt snippet

```text
Given a command and schedule, write a safe crontab entry including PATH/SHELL notes, logging, and verification steps.
```
