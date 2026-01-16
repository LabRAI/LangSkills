# Troubleshooting

## Arguments break on spaces/newlines
- 使用 `find -print0` + `xargs -0`，或改用 `-exec ... {} +`。
