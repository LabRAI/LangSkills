# LLM (Local/Remote) integration

本目录提供一个极简的 LLM Provider 抽象，用于把“本地开源模型/远端模型”接入 skill 生成流程（目前用于 **rewrite/提质** 阶段）。

## Providers

### `mock`（离线可复现）

用于 CI/self-check 或本地离线调试。

```bash
node agents/run_local.js \
  --domain linux --topic filesystem/find-files \
  --out /tmp/skill-llm-out --overwrite --capture \
  --llm-provider mock --llm-fixture agents/llm/fixtures/rewrite.json
```

### `ollama`（本地开源模型）

前置：本机已启动 Ollama（默认 `http://127.0.0.1:11434`）。

```bash
node agents/run_local.js \
  --domain linux --topic filesystem/find-files \
  --out /tmp/skill-llm-out --overwrite --capture \
  --llm-provider ollama --llm-model qwen2.5:7b
```

可选参数：

- `--llm-base-url <url>`：Ollama 地址（默认 `http://127.0.0.1:11434`）
- `--llm-timeout-ms <n>`：单次请求超时（默认 60000）

### `openai`（远端 OpenAI-compatible）

支持 OpenAI Chat Completions 兼容接口（`POST /v1/chat/completions`）。

环境变量（可写入 repo root 的 `.env`；会被 best-effort 自动加载）：

- `OPENAI_API_KEY`：API key
- `OPENAI_BASE_URL`：可选；例如 `https://api.example.com`（若未带 `/v1` 会自动补齐）
- `OPENAI_MODEL`：可选；不传 `--llm-model` 时使用

```bash
node agents/run_local.js \
  --domain linux --topic filesystem/find-files \
  --out /tmp/skill-llm-out --overwrite --capture \
  --llm-provider openai --llm-model gpt-4o-mini
```

