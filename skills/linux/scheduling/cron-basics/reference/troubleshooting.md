# Troubleshooting

## Works in shell but not in cron
- cron 的 PATH/环境变量更少；使用绝对路径并显式设置 PATH；把 stderr 重定向到日志排查。

## Job runs too often / wrong timezone
- 检查表达式字段与系统时区；必要时在日志里打印时间戳确认。
