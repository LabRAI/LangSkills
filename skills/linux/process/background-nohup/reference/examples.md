# Examples

```bash
# Run a command with timestamped log
nohup mycmd >"run.$(date +%F_%H%M%S).log" 2>&1 &
```
