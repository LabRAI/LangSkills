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

