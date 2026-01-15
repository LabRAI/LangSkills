# Troubleshooting

## 'sed -i' behaves differently on macOS vs Linux
- 不同实现对 `-i` 参数不同；在 Linux 上建议使用 `-i.bak` 明确生成备份。

## Special characters break the replacement
- 替换字符串包含 `/`/`&` 等需要转义；或使用不同分隔符（如 `|`）。
