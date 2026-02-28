from __future__ import annotations

import os

from ..env import resolve_llm_provider_name
from ..utils.urls import OLLAMA_DEFAULT_BASE_URL
from .ollama_client import OllamaClient
from .openai_client import OpenAiClient
from .types import LlmClient


def _must_env(name: str) -> str:
    v = str(os.environ.get(name, "")).strip()
    if not v:
        raise RuntimeError(f"Missing env: {name}")
    return v


def create_llm_from_env(*, provider_override: str | None = None, model_override: str | None = None) -> LlmClient:
    provider = resolve_llm_provider_name(provider_override or os.environ.get("LLM_PROVIDER") or "openai")
    model_override = str(model_override or "").strip() or None

    if provider == "ollama":
        base_url = str(os.environ.get("OLLAMA_BASE_URL") or OLLAMA_DEFAULT_BASE_URL).strip()
        model = str(model_override or os.environ.get("OLLAMA_MODEL") or "").strip()
        if not model:
            raise RuntimeError("Missing env: OLLAMA_MODEL (required when LLM_PROVIDER=ollama)")
        return OllamaClient(base_url=base_url, model=model)

    base_url = str(os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or "").strip()
    if not base_url:
        raise RuntimeError("Missing env: OPENAI_BASE_URL (set to your OpenAI-compatible endpoint)")
    api_key = _must_env("OPENAI_API_KEY")
    model = str(model_override or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
    return OpenAiClient(base_url=base_url, api_key=api_key, model=model)
