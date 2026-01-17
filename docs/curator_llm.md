# Curator：机器人如何“整理 skill”（以及如何改用 LLM API）

本仓库里，“整理 skill”指的是把抓取/解析得到的 **候选条目**（`candidates.jsonl`）整理成可审计、可增量消费的 **提案队列**（`curation.json`），供后续人工/自动生成 skill 使用。

## 1) 现有机器人是怎么整理的（无 LLM）

### 输入：candidates（整理前材料）

- 输入文件：`runs/<run-id>/candidates.jsonl`
- 每行一个 JSON（JSONL），常见 `kind`：
  - `repo_file`：来自 Tier0 上游 repo ingest（例如扫描到某个 `SKILL.md`）
  - `doc_heading`：来自网页抓取快照抽取到的标题/小节

示例（可直接打开）：
- `runs/curator-demo/candidates.jsonl`
- `runs/curator-llm-sample/candidates.jsonl`

### 处理：curator 聚合 + 去重 + 建议

入口：`agents/curator/run.js`

核心行为：

1. **增量读取**：用 `runs/<run-id>/curator_state.json` 里的 `cursor_bytes` 记录读到 candidates.jsonl 的字节位置，支持断点续跑（append-only）。
2. **proposal 分组去重**：对每条 candidate 做 `decideProposal()`，生成一个稳定的 `proposalKey`，并把同 key 的条目聚合成一组（统计 counts、抽样 candidate_ids/sources）。
3. **稳定 ID**：`proposal_id = sha256(proposalKey)`（固定 12 位前缀），保证跨运行稳定。
4. **输出汇总**：写 `runs/<run-id>/curation.json`（给人看也给机器看），并写 `runs/<run-id>/curation_log.jsonl`（append-only 日志）。

### 输出：curation（整理后结果）

输出文件：
- `runs/<run-id>/curation.json`：提案列表 + 去重统计 + 证据引用（sources/candidate_ids）
- `runs/<run-id>/curator_state.json`：断点续跑状态（cursor + groups 聚合）

你可以直接查看一个真实产物：
- `runs/curator-demo/curation.json`

## 2) 现有实现对“要求”的覆盖情况

如果你的要求是：

- ✅ 去重统计（proposal 聚合）
- ✅ `topic/slug` 建议（提供 `suggested`）
- ✅ `auto|manual|ignore` 分类（可自动 vs 需人工 vs 噪声）
- ✅ 断点续跑（`cursor_bytes`）
- ✅ 可审计证据（sample sources/candidate_ids）

那么现有 curator 已经具备，并且有可复现产物：`runs/curator-demo/*`。

当前不足（也是引入 LLM 的价值点）：

- 规则/启发式对 “语义化映射到 taxonomy” 能力有限（尤其是 `doc_heading`）。
- 更复杂的归类/合并/命名（例如同义、相近主题合并）需要更强的语义理解。

## 3) 改用 LLM API 来整理（LLM 增强版 curator）

curator 现在支持可选 LLM 增强：在规则 baseline 的基础上，让 LLM 给出更好的 `action/suggested`。

### Prompt 地址（你后续可以直接润色）

- System prompt：`agents/curator/prompts/curate_proposals_v1.system.md`
- User prompt：`agents/curator/prompts/curate_proposals_v1.user.md`

curator 会把 prompt 内容做 sha256，并写入：
- `runs/<run-id>/curation.json` 顶层 `llm.prompts.sha256`
- 每条 proposal 的 `llm.prompts.sha256`

### 离线跑通（mock，无需 key）

```bash
# 1) 准备一个很小的 candidates 样例（仓库已内置）
node agents/curator/run.js --domain linux --run-id curator-llm-sample --reset

# 2) 用 mock LLM（固定返回 fixtures 里的 JSON）
node agents/curator/run.js --domain linux --run-id curator-llm-sample \
  --llm-provider mock --llm-fixture agents/curator/fixtures/curate_proposals.mock.json
```

你会看到：
- `runs/curator-llm-sample/curation.json` 顶层出现 `llm`
- proposal 中出现 `baseline`（规则结果）+ `llm`（LLM 建议），并以 LLM 为最终 `action/suggested`

### 接入 OpenAI（等你提供 key 后即可验证）

```bash
node agents/curator/run.js --domain linux --run-id curator-demo \
  --llm-provider openai --llm-model gpt-4o-mini --llm-api-key "$OPENAI_API_KEY"
```

说明：
- key 不会落盘到产物（只用于请求）。
- 若你要改 prompt，只需要改 `agents/curator/prompts/*` 两个文件即可。

也可以用 `.env`（推荐本地开发）：

```bash
# .env (repo root)
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://<your-openai-compatible-host>
```

然后运行时不再传 `--llm-api-key/--llm-base-url`（会自动读取环境变量）。
