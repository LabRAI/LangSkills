# SkillGen (curation → skills)

`agents/skillgen/run.js` 把 `runs/<run-id>/curation.json` 里的 proposals（通常来自 `agents/curator/run.js`）转成可验证的 skills 目录结构：

- 读取：`runs/<run-id>/curation.json`
- 写入：`<out>/<domain>/<topic>/<slug>/*`
- 产物：
  - `skill.md` / `library.md` / `metadata.yaml`
  - `reference/sources.md`（包含 fetch 指纹字段）
  - `reference/materials/*`（生成所用原材料：proposal + source snippets）
  - `reference/llm/*`（LLM prompt/response capture，可选）

## Usage

```bash
# 0) 先产出 curation.json（例：orchestrator + curator）
node agents/orchestrator/run.js --domain linux --run-id demo --crawl-max-pages 5 --extract-max-docs 20 --generate-max-topics 0
node agents/curator/run.js --domain linux --run-id demo --llm-provider openai --llm-capture

# 1) 从 curation 生成一批 skills（默认挑 action=auto）
node agents/skillgen/run.js --domain linux --run-id demo --llm-provider openai --llm-capture --max-skills 5
```

Prompts（可直接改）：

- `agents/skillgen/prompts/generate_skill_v1.system.md`
- `agents/skillgen/prompts/generate_skill_v1.user.md`

