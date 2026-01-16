# Troubleshooting

## rsync copies everything every time
- 检查是否每次都变更了 mtime/权限；或源/目标路径写错导致没命中增量。

## Permission denied on remote
- 确认远端目录权限；必要时把目标改到你有权限的目录或通过 sudo+rsync（更复杂，需谨慎）。
