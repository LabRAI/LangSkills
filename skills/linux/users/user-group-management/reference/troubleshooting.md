# Troubleshooting

## Group change not effective
- 用户需要重新登录/重新打开 shell；或使用 `newgrp` 临时切换。

## Can't switch user / no home
- 创建用户时确保 `-m`；并检查 shell 是否存在（-s）。
