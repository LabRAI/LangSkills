# Library

## Copy-paste commands

```bash
# 1) Store token securely (example: env var in your shell/CI secret)
export GITHUB_TOKEN='***'

# 2) Create an issue
OWNER='<owner>'
REPO='<repo>'

curl -sS -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${REPO}/issues" \
  -d '{"title":"Automation report","body":"Created by a script. (Do not paste tokens here)"}'
```

## Prompt snippet

```text
You are an automation engineer. Write a safe workflow to create a GitHub issue via the REST API.
Constraints:
- Never print tokens.
- Include idempotency guidance and rate-limit handling.
- Steps <= 12 with verification.
```
