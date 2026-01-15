# Edge cases

- 容器/网络命名空间下的端口需要在对应 namespace 里查看（docker/podman）。
- UDP 没有 LISTEN 的概念，使用 `ss -lunp` 查看。
