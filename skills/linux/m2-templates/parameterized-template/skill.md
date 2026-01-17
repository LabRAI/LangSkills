# M2 参数化模板：占位技能（用于 10 万级扩量验收）

## Goal
- 作为 Parameterized skills 的模板：通过 `{{...}}` 占位符在分发端按 skill id 注入参数，避免堆重复文档。

## When to use
- 需要用“模板 + 参数”方式扩量，并保持网站/CLI 可访问。

## When NOT to use
- 需要真实业务知识/最佳实践时（本模板只用于扩量验收与工程回归）。

## Prerequisites
- Environment: Linux
- Permissions: None
- Tools: bash
- Inputs needed: None

## Steps (<= 12)
1. 输出当前实例的唯一标识：`echo "{{id}}"` [[1]]
2. 输出当前实例的 slug：`echo "{{slug}}"` [[1]]
3. 确认输出中包含期望的 `{{id}}`/`{{slug}}`（用于验证参数替换是否生效） [[2]]

## Verification
- 看到输出包含当前 skill 的 id/slug（例如：`linux/m2-param/p-000001`）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: None.
- Privacy/credential handling: No secrets; do not paste credentials into terminals or logs.
- Confirmation requirement: None.

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] https://man7.org/linux/man-pages/man1/echo.1.html
- [2] https://wiki.archlinux.org/title/Coreutils
- [3] https://pubs.opengroup.org/onlinepubs/9699919799/utilities/echo.html
