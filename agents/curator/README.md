# Curator

Curator 是机器人闭环中“中间那一层”：把 `runs/<run-id>/candidates.jsonl` 整理成可审计、可增量、可作为后续生成/发布输入的队列与摘要。

当前 MVP 目标（Missing-015）：
- 去重统计（按“proposal key”聚合 candidates）
- 为每个聚合结果给出 `topic/slug` 建议（不直接改 configs、不直接生成 skill 文件）
- 标注 `auto|manual|ignore`（可自动生成 vs 需人工）
- 断点续跑：记录 `cursor_bytes` + 聚合状态，支持增量处理 append-only 的 candidates.jsonl

## Usage

```bash
# 1) 先跑 orchestrator 产出 candidates.jsonl（crawl + extract + Tier0 ingest）
node agents/orchestrator/run.js --domain linux --run-id curator-demo --crawl-max-pages 1 --extract-max-docs 10 --generate-max-topics 0

# 2) 再跑 curator 做整理
node agents/curator/run.js --domain linux --run-id curator-demo
```

Outputs（在 `runs/<run-id>/`）：
- `curation.json`：整理后的汇总（包含 proposals + 建议 + 证据引用）
- `curator_state.json`：增量状态（cursor + 聚合结果；支持 resume）
- `curation_log.jsonl`：每次运行一条记录（append-only）

## LLM 增强（可选）

Curator 默认使用规则/启发式做 `auto|manual|ignore` 与 `topic/slug` 建议；如需更“语义化”的整理，可开启 LLM：

- 输出仍落在同一份 `runs/<run-id>/curation.json`，但会额外写入：
  - 顶层 `llm`（本次 LLM 运行信息：provider/model/prompt hash/统计）
  - 每条 proposal 的 `baseline`（规则结果）与 `llm`（LLM 建议），并以 LLM 为最终 `action/suggested`

Prompts（可直接改）：
- `agents/curator/prompts/curate_proposals_v1.system.md`
- `agents/curator/prompts/curate_proposals_v1.user.md`

离线可复现（mock）：

```bash
node agents/curator/run.js --domain linux --run-id curator-llm-sample --reset
node agents/curator/run.js --domain linux --run-id curator-llm-sample \
  --llm-provider mock --llm-fixture agents/curator/fixtures/curate_proposals.mock.json
```

OpenAI（需要 key）：

```bash
node agents/curator/run.js --domain linux --run-id curator-demo \
  --llm-provider openai --llm-model gpt-4o-mini --llm-api-key "$OPENAI_API_KEY"
```

