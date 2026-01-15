# Troubleshooting

## "not in gzip format" / "file format not recognized"
- 确认文件扩展名与实际格式一致；用 `file <path>` 判断真实类型。

## Disk space spikes during compression
- 使用 `-k` 会同时保留原件与压缩包；确认目标磁盘空间足够。
