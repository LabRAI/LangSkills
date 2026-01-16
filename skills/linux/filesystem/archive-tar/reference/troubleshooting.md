# Troubleshooting

## Not in gzip format / wrong compression flag
- 先 `tar -tf <archive>` 看是否能列出；gzip/xz flag 不匹配时会报错，按实际格式选 `-z`/`-J`。

## Permission/ownership surprises on extract
- 不要在不理解权限影响时用 root 解压；必要时在空目录中解压并审阅再移动到目标位置。
