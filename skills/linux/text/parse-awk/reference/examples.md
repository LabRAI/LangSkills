# Examples

```bash
# Print first 5 columns with line numbers
awk '{print NR ":" $1, $2, $3, $4, $5}' file.txt | head
```
