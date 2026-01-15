# Troubleshooting

## "File exists" / accidental overwrite risk
- 优先用 `-n`（不覆盖）或 `-i`（交互确认）。
- 如必须覆盖，建议配合 `--backup=numbered` 保留旧版本。

## Copying symlinks vs targets
- `cp -a` 更接近“保留原语义”（包含符号链接本身）；避免无意跟随链接导致拷贝扩大。
