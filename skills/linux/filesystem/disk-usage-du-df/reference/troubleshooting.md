# Troubleshooting

## du is slow / permission denied
- 缩小范围（从挂载点下的子目录开始），必要时用 sudo；可把错误输出重定向：`2>/dev/null`。

## df doesn't drop after deleting files
- 可能有进程仍持有已删除文件句柄（空间未释放）；用 `lsof +L1` 查找并重启/关闭进程。
