# Examples

```bash
# Send a CI summary
curl -X POST -H 'Content-type: application/json' --data '{"text":"CI: ✅ tests passed"}' "$SLACK_WEBHOOK_URL"
```
