# Edge cases

- 多 kubeconfig 合并：`KUBECONFIG` 指向多个文件时，context 名称可能冲突
- 同名 namespace：不同集群可有同名 namespace，必须优先确认 context
- 只读命令也可能泄露信息：在共享终端/录屏时注意脱敏
