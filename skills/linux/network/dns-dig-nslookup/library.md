# Library

## Copy-paste commands

```bash
dig example.com A +short
dig @1.1.1.1 example.com AAAA +short
dig example.com CNAME
dig -x 8.8.8.8 +short
cat /etc/resolv.conf
```

## Prompt snippet

```text
Given a domain and symptoms (wrong IP / NXDOMAIN / slow), write a dig-based DNS triage plan including checks with a specific resolver.
```
