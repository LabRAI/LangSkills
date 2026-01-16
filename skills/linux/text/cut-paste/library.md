# Library

## Copy-paste commands

```bash
# Extract columns 1 and 3 from comma-separated data
cut -d',' -f1,3 data.csv

# Merge two column files into a CSV
paste -d',' col1.txt col2.txt > merged.csv
```

## Prompt snippet

```text
You are a Linux assistant. Help the user extract or merge columns using cut/paste.
Rules:
- Ask for delimiter and column numbers; warn about complex CSV quoting.
- Include a quick spot-check step (head).
```
