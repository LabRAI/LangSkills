# Troubleshooting

## patch: can't find file to patch / wrong -pN
- `-pN` 控制去掉路径前缀的层数；根据补丁里 `--- a/...` 的路径调整。

## patch failed / hunks FAILED
- 目标文件版本不匹配；需要手工合并或重新生成补丁。
