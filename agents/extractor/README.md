# Extractor (DocItem → TopicCandidates)

这个 extractor 负责把 crawler 抓取到的 raw snapshot（`.cache/web`）转换成 **可去重、可持续迭代** 的候选任务清单（TopicCandidates），用于回答 Q4 的“不会跑俩小时就结束”与 Q6 的“怎么 scale”。

## Inputs / Outputs

- Input:
  - `runs/<run-id>/crawl_state.json`（crawler 状态；包含 per-URL `docs` 与 `fetch.cache_file/sha256`）
  - `.cache/web/<hash>.txt`（raw snapshot）
- Output:
  - `runs/<run-id>/candidates.jsonl`（候选任务，按 doc heading 生成）
  - `runs/<run-id>/extractor_state.json`（断点续跑：按 URL+sha256 记录已处理）
  - `runs/<run-id>/extractor_log.jsonl`（每个 URL 的处理日志）

## Usage

```bash
# 先抓取（产生 crawl_state.json + cache files）
node agents/crawler/run.js --domain linux --run-id linux-orch-demo --max-pages 50 --max-depth 2

# 再抽取候选（产生 candidates.jsonl）
node agents/extractor/run.js --domain linux --run-id linux-orch-demo --max-docs 50
```

