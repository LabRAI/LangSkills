# Troubleshooting

## Operation not supported
- 文件系统/挂载可能不支持 ACL；检查 mount 选项与文件系统类型（参考 Arch Wiki）。

## ACL looks correct but access still denied
- 检查 `mask::`（有效权限可能被 mask 限制）；需要时调整 mask 或重新设置 ACL。
