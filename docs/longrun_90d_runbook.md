# 90 天长跑（500 页/天）Runbook

目标：让多个机器人可以连续运行 90 天，并且每天最多抓取/处理约 500 个页面（可控成本），同时确保：

- Tier0（上游 GitHub library/spec/skills）能“吃完”并可持续刷新
- Tier1（官方文档站点）队列足够大，不会很快跑空
- 每轮都有可审计的状态与指标（方便定位“为什么停了/为什么没新增”）

---

## 1) 数据源（以配置为准）

### 1.1 全局 sources registry

- `agents/configs/sources.yaml#L1`

关键点：

- Tier1：`type: http_seed_crawl`（seed → discovery → queue）
- Tier0：`type: github_repo`（repo ingest，生成候选；按远端 commit 刷新）

### 1.2 linux domain 绑定的 primary sources

- `agents/configs/linux.yaml#L1`

当前 linux 绑定：

- `linux_tier1_web`（TTL=7d）
- `linux_tier1_web_extra`（TTL=14d）

并允许 `kernel.org` 等域名用于扩展（见 `source_policy.allow_domains`）。

---

## 2) 90 天运行策略（500 页/天）

推荐用 orchestrator 做“日循环”，每个 cycle 只做固定上限的工作量，然后 sleep 到下一天：

```bash
node agents/orchestrator/run.js \
  --domain linux \
  --run-id linux-90d \
  --loop \
  --crawl-max-pages 500 \
  --crawl-max-depth 2 \
  --extract-max-docs 500 \
  --generate-max-topics 0 \
  --cycle-sleep-ms 86400000
```

说明：

- `--crawl-max-pages 500`：每天最多抓 500 个 URL
- `--extract-max-docs 500`：每天最多处理 500 个已抓取页面
- `--generate-max-topics 0`：只做“抓取与候选”，不生成 skills（可后续单独开生成机器人）
- `--cycle-sleep-ms 86400000`：每轮结束后睡 24h

产物目录（长期保存的“审计证据”）：

- `runs/<run-id>/crawl_state.json` + `crawl_log.jsonl`
- `runs/<run-id>/extractor_state.json` + `extractor_log.jsonl`
- `runs/<run-id>/repo_state.json` + `repo_docs.jsonl`（Tier0）
- `runs/<run-id>/metrics.json` + `metrics_log.jsonl`

---

## 3) 确定性验收（Checklist 自动化）

验收脚本：

- `scripts/verify-longrun.js#L1`

验收命令（按你给的口径：90 天、500 页/天）：

```bash
node scripts/verify-longrun.js \
  --domain linux \
  --run-id linux-90d \
  --days 90 \
  --pages-per-day 500 \
  --strict
```

报告输出：

- `runs/<run-id>/acceptance_longrun.json`

脚本会检查：

1) Tier0 repo 是否“吃完”（`repo_state.json` 中每个 source 完成、文件数对齐）
2) Tier1 crawl 队列是否满足：`queue.length >= days * pages_per_day`（否则可能提前跑空）
3) extractor 是否产出 candidates（`extractor_state.json` 中 candidates_emitted > 0）
4) metrics 文件是否持续写入（便于做趋势与告警）

---

## 4) 如果验收失败（最常见原因与修复手段）

### 4.1 `queue.length` 不够大（会提前跑空）

解决优先级（从最安全到最激进）：

1) 增加 seeds（优先官方目录/索引页）：改 `agents/configs/sources.yaml#L1`
2) 放宽 allow_domains（只加官方/稳定域名）：改 `agents/configs/linux.yaml#L1`
3) 增加 `--crawl-max-depth`（会显著放大发现面；注意噪声与策略）

### 4.2 blocked/error 比例过高

- blocked 高：通常是 allow_domains 太窄，或者站点链接大量跳出 allowlist
- error 高：通常是网络/站点限制/超时；可考虑减小并发、提高 timeout、或加备用 seeds

### 4.3 Tier0 repo 没吃完

- 看 `runs/<run-id>/repo_state.json`，确认 `processed_files/files_total` 是否推进
- 如果 repo 很大且想“分天吃”，需要在 orchestrator 增加 repo ingest 的 per-cycle budget（后续可加）

---

## 5) sources 扩展建议（后续持续加）

扩展原则：

- Tier1：优先官方文档、man pages、发行版 wiki、标准规范；保持 allowlist 可控
- Tier0：优先结构清晰的 skills/spec 仓库；只做 reference-only ingest（不直接复制内容）

落地动作：

1) 在 `agents/configs/sources.yaml#L1` 增加新的 source（http_seed_crawl 或 github_repo）
2) 在 `agents/configs/<domain>.yaml#L1` 的 `sources.primary` 里引用它（若是 Tier1）
3) 同步维护 `source_policy.allow_domains`（避免 crawler 发现后被大量 block）

