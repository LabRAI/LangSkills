# Troubleshooting

## tail -f stops after log rotation
- 用 `tail -F` 代替 `-f`，对被轮转替换的文件更友好。

## less shows strange characters
- 可能是二进制/控制字符；避免直接粘贴内容，必要时先确认文件类型。
