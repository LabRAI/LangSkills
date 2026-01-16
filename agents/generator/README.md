# Generator

当前可运行的最小生成器：`agents/run_local.js`

- 输入：`agents/configs/<domain>.yaml`（topics 列表）
- 输出：`skills/<domain>/<topic>/<slug>/`（骨架模板文件）

## Capture 模式（生成“真实内容”）

`--capture` 会按 topic 的 capture spec 抓取来源页面（写入 `.cache/`，默认不提交），并生成：

- `skill.md`：包含可执行步骤 + 关键步骤引用 `[[n]]`
- `reference/sources.md`：记录 URL / 摘要 / 访问日期 / 支撑步骤 + 抓取指纹（bytes/sha256/cache hit/miss）

常用参数：

- `--capture`：开启抓取并生成非 TODO 内容
- `--capture-strict`：抓取失败直接报错（推荐本地/CI 校验用）
- `--cache-dir <path>`：抓取缓存目录（默认 `.cache/web`）
- `--timeout-ms <n>`：单个来源抓取超时（默认 20000）

严格校验（捕获内容必须有 citations + fetch evidence + 无 TODO）：

```bash
node scripts/validate-skills.js --strict
```

本地运行示例：

```bash
node agents/run_local.js --domain linux --out skills
node agents/run_local.js --domain linux --topic filesystem/find-files --out skills --overwrite

# Generate all linux skills with real capture (recommended)
node agents/run_local.js --domain linux --out skills --overwrite --capture --capture-strict
```
