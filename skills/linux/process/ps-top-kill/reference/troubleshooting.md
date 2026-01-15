# Troubleshooting

## Process won't die even with -KILL
- 可能处于不可中断的 D 状态（IO 等待）或是僵尸进程（Z）；Z 需要处理父进程。

## It keeps coming back
- 可能被 systemd/supervisor 自动重启；应该停对应服务并检查重启策略。
