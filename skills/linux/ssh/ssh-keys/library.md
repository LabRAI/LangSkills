# Library

## Copy-paste commands

```bash
ssh-keygen -t ed25519 -C "me@example.com" -f ~/.ssh/id_ed25519
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host
ssh -v user@host
```

## Prompt snippet

```text
Create a secure SSH key setup guide for a user, including agent usage, authorized_keys permissions, and a verification login command.
```
