# Edge cases

- 不同发行版的 admin 组不同（sudo vs wheel）；按系统策略选择。
- 服务账号通常不应允许交互登录；需要时设置更严格的 shell/权限。
