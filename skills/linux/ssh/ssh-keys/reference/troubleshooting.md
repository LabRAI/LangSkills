# Troubleshooting

## Permission denied (publickey)
- 检查远端 `~/.ssh` 与 `authorized_keys` 权限；确认公钥已正确追加且没有多余空格/换行。

## Wrong key is used
- 用 `ssh -v` 看加载的 key；必要时在 `~/.ssh/config` 指定 `IdentityFile`。
