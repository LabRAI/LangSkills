"""Minimal mock client for journal pipeline dry-run support."""
from __future__ import annotations
from typing import Any


class MockLlmClient:
    """Stub LLM client that returns empty responses (for offline/dry-run mode)."""
    def __init__(self, **kwargs: Any) -> None:
        pass
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        return ""
    async def chat(self, messages: list, **kwargs: Any) -> str:
        return ""


MockLLM = MockLlmClient


def create_mock_llm(**kwargs: Any) -> MockLlmClient:
    return MockLlmClient(**kwargs)
