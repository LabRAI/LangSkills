# Examples

```bash
# Batch run a command on files safely
find . -type f -name '*.txt' -print0 | xargs -0 -n 1 wc -l
```
