# Orchestrator (scheduler + coverage + long-running ops)

这个 orchestrator 用来把 “一次性脚本” 变成 “可连续运行数天/数星期的系统”（Q4），并用 sources registry + adapters 把 “爬哪里/怎么 scale” 变成配置问题（Q6）。

## What it does (MVP)

- 把 `crawler` 和 `runner` 组合成一个 **可循环调度** 的进程：
  - `crawler`：seeds → discovery → 去重入队（落盘 state/log；缓存 `.cache/web`）
  - `extractor`：DocItem（FETCHED snapshots）→ TopicCandidates（落盘 candidates/state）
  - `runner`：topics 队列执行（落盘 state）
- 输出可审计的 **覆盖率/吞吐/错误** 指标到 `runs/<run-id>/metrics.json`（并追加 `metrics_log.jsonl` 便于做时间序列）

## State machine (doc items)

最小状态机（落到文件或 DB 都行）：

- `DISCOVERED` → `FETCHED` → `PARSED` → `CANDIDATES_EXTRACTED` → `SKILL_DRAFTED` → `VALIDATED` → `MERGED`

当前代码实现到：

- DISCOVERED/FETCHED/BLOCKED/ERROR：由 `agents/crawler/run.js` 的 per-URL 状态字段提供（见 `crawl_state.json` 的 `docs`）
- CANDIDATES_EXTRACTED：由 `agents/extractor/run.js` 产出 `runs/<run-id>/candidates.jsonl`（当前 extractor 不回写 `crawl_state.json` 的 doc.state）

## DB schema (Postgres blueprint)

> 代码默认走文件落盘；如果要上 Postgres，建议表结构如下（最小可用）。

```sql
create table sources (
  id text primary key,
  type text not null,
  config jsonb not null,
  allowlist boolean not null default false,
  license_policy text,
  refresh jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create type doc_state as enum (
  'DISCOVERED','FETCHED','PARSED','CANDIDATES_EXTRACTED','SKILL_DRAFTED','VALIDATED','MERGED','BLOCKED','ERROR'
);

create table doc_items (
  id text primary key,
  source_id text references sources(id),
  url text,
  path text,
  state doc_state not null,
  etag text,
  last_modified text,
  sha256 text,
  bytes integer,
  discovered_at timestamptz,
  fetched_at timestamptz,
  parsed_at timestamptz,
  last_error text,
  attempts integer not null default 0
);

create table topic_candidates (
  id text primary key,
  doc_item_id text references doc_items(id),
  title text not null,
  kind text not null,
  evidence jsonb not null,
  created_at timestamptz not null default now()
);
```

## Sources registry

- `agents/configs/sources.yaml`：全局 sources registry（Tier1 官方文档 + Tier0 上游 skills repos）
- `agents/configs/<domain>.yaml`：domain bot config（scope/策略/topics），可引用 `sources.primary[]`

## Usage

```bash
# One cycle (crawl + optional generate), write metrics to runs/<run-id>/metrics.json
node agents/orchestrator/run.js --domain linux --run-id linux-orch-demo --crawl-max-pages 50 --extract-max-docs 50 --generate-max-topics 5

# Long run (days/weeks): loop forever with sleeps
node agents/orchestrator/run.js --domain linux --run-id linux-orch-weekly --loop --sleep-ms 5000 --cycle-sleep-ms 600000
```
