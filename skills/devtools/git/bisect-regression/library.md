# Library

## Copy-paste workflow

```bash
# Start
git bisect start
git bisect bad <bad>
git bisect good <good>

# Repeat until it prints the first bad commit:
# - run your test command
# - mark good/bad based on the result
git bisect good
git bisect bad

# Done
git bisect reset
```

## Example: automate with a script

```bash
# The script should exit 0 for good, non-zero for bad.
git bisect start
git bisect bad <bad>
git bisect good <good>
git bisect run ./scripts/test.sh
git bisect reset
```

## Prompt snippet

```text
You are a developer. Given a good commit, a bad commit, and a test command, write a safe git bisect procedure.
Constraints:
- Steps <= 12 with verification.
- Mention keeping the workspace clean and recording results.
```
