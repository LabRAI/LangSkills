# Synthetic Skill s-0863

## Goal
- Provide a deterministic, validator-clean skill for scale testing.

## When to use
- When you need to test indexing, validation, and reporting at large N without network access.

## When NOT to use
- When you need real operational guidance.

## Prerequisites
- Environment: Linux
- Permissions: None
- Tools: bash
- Inputs needed: None

## Steps (<= 12)
1. Print a marker with `echo "s-0863"` [[1]]
2. Confirm the output contains the same marker string [[2]]

## Verification
- Expected output contains: s-0863

## Safety & Risk
- Risk level: **low**
- Irreversible actions: None.
- Privacy/credential handling: No secrets; do not paste credentials into terminals or logs.
- Confirmation requirement: None.

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] https://man7.org/linux/man-pages/man1/echo.1.html
- [2] https://www.gnu.org/software/coreutils/manual/html_node/echo-invocation.html
- [3] https://pubs.opengroup.org/onlinepubs/9699919799/utilities/echo.html
