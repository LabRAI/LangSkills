# Library

## Copy-paste commands

```bash
ps -eo pid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head
top
kill -TERM 12345
sleep 5; kill -KILL 12345
```

## Prompt snippet

```text
Given a suspected runaway process, output a safe investigation (ps/top) and termination (TERM then KILL) plan with verification and service-manager notes.
```
