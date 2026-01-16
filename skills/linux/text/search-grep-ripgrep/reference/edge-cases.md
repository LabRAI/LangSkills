# Edge cases

- 正则引擎差异：grep/rg 的正则语法不完全一致；遇到复杂模式先用简单模式验证。
- 默认忽略规则：rg 会尊重 `.gitignore`；需要包含隐藏文件时加 `--hidden`。
