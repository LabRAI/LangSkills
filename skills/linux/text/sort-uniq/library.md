# Library

## Copy-paste commands

```bash
# Sort and write to a new file
sort input.txt > sorted.txt

# Unique lines (requires sort if duplicates are not adjacent)
sort input.txt | uniq

# Count duplicates and show top 10
sort input.txt | uniq -c | sort -nr | head -10
```

## Prompt snippet

```text
You are a Linux assistant. Provide a minimal, safe sort/uniq pipeline for the user's goal.
Rules:
- Mention that uniq only collapses adjacent duplicates (sort first unless already grouped).
- Include a verification step (sort -c or spot check).
```
