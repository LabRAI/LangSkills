# Crawler (seeds → discovery → queue)

这个 crawler 用于回答/落地 **Q6**：机器人部署后“从哪里爬、怎么 scale”。

- 输入：`agents/configs/<domain>.yaml` 的 `seeds` + `source_policy`（allow/deny domains）
- 输出：
  - 抓取缓存：`.cache/web/*.txt`（按 URL sha256 前 16 位命名；默认不提交）
  - 状态与日志：`runs/<run-id>/crawl_state.json`、`runs/<run-id>/crawl_log.jsonl`（默认不提交）

## Usage

```bash
# Crawl linux seeds once (default max-depth=2, max-pages=200)
node agents/crawler/run.js --domain linux

# Run longer (no max page cap) + loop with sleeps (suitable for days/weeks bots)
node agents/crawler/run.js --domain linux --max-pages 0 --loop --sleep-ms 3000 --cycle-sleep-ms 600000

# Override seeds / policy for a one-off run (useful in testing or bootstrapping)
node agents/crawler/run.js --domain linux --seeds http://127.0.0.1:8000/index.html --allow-domain 127.0.0.1
```

## How to scale

- 扩大抓取面：在 `agents/configs/<domain>.yaml` 增加 `seeds`，并同步维护 `source_policy.allow_domains/deny_domains`。
- 多机器人并行：按 domain 或 seeds 分片（不同 `--run-id`/不同 seeds），避免同一队列互相踩。
- 可审计：以 `runs/<run-id>/crawl_log.jsonl` 为准；每条记录包含 URL、cache hit/miss、bytes、sha256、以及 enqueue/block 统计。

