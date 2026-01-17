# Library

## Copy-paste commands

```bash
# Set your webhook URL via env var (do NOT commit it)
export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/.../.../...'

# Minimal message
curl -X POST -H 'Content-type: application/json' --data '{"text":"hello"}' "$SLACK_WEBHOOK_URL"

# Blocks example (keep it small; validate in a test channel first)
curl -X POST -H 'Content-type: application/json' --data '{"blocks":[{"type":"section","text":{"type":"mrkdwn","text":"*Build* succeeded"}}]}' "$SLACK_WEBHOOK_URL"
```

## Prompt snippet

```text
You are an integration engineer. Write a safe plan to send Slack notifications via Incoming Webhooks.
Constraints:
- Do not paste webhook URLs or tokens in output.
- Provide steps <= 12 with a verification step.
- Include a brief security note on secret storage and rotation.
```
