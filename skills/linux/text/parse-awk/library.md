# Library

## Copy-paste commands

```bash
# Sum the 2nd column (skip header)
awk 'NR==1{next} {sum+=$2} END{print sum}' data.tsv

# Filter lines where 3rd column > 100
awk '$3>100 {print $1, $3}' metrics.txt | head
```

## Prompt snippet

```text
Given a sample line format and a goal (extract/filter/sum), write a minimal awk one-liner plus a verification command.
```
