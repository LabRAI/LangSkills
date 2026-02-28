# `langskills/llm/`

LLM provider abstraction and clients used for SkillGate, skill generation, and improvement.

## Key files

- `factory.py`: builds an LLM client from environment variables.
- `openai_client.py`: OpenAI-compatible chat JSON client.
- `ollama_client.py`: Ollama chat JSON client.
- `base.py`, `types.py`: common interfaces/types shared by providers.

## Configuration (env vars)

OpenAI-compatible:

- `LLM_PROVIDER=openai` (default)
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default set in `.env.example`)

Ollama:

- `LLM_PROVIDER=ollama`
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL`

See also: `../../README.md` and `.env.example`.
