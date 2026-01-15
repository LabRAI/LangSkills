# Troubleshooting

## Operation not permitted / Permission denied
- 你可能缺少权限：用 `sudo` 运行，或先确认当前用户是否为 owner。

## Symlink ownership surprises
- `chown` 默认更改“链接指向的目标”；如果你想改链接本身，参考 `-h` 选项（并理解影响）。
