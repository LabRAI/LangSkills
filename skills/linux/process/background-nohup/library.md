# Library

## Copy-paste commands

```bash
nohup bash -lc 'long_task --arg value' > long_task.log 2>&1 &
echo "PID=$!"
jobs -l
disown -h %1
tail -n 50 long_task.log
```

## Prompt snippet

```text
Given a long-running command, output a nohup/disown backgrounding recipe with logging, PID capture, and a safe stop/verification suggestion.
```
