# Library

## Copy-paste commands

```bash
curl -I https://example.com
curl -L -O https://example.com/file.tar.gz
curl --retry 5 --retry-delay 1 --connect-timeout 5 --max-time 30 -L -O https://example.com/file.tar.gz
wget -c https://example.com/big.iso
```

## Prompt snippet

```text
Given a URL and constraints (proxy, retry, timeout), output a safe curl/wget download plan with verification and credential-safety notes.
```
