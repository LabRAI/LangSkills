# Edge cases

- alias/function 可能遮蔽同名二进制；用 `type -a` 查明。
- PATH 顺序决定优先级；必要时打印 `$PATH` 排查。
