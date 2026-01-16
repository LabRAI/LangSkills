# Examples

```bash
# Find top CPU users (ps) and terminate safely
ps -eo pid,%cpu,%mem,cmd --sort=-%cpu | head
kill -TERM <pid>
```
