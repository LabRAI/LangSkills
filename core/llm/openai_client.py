from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..env import normalize_openai_base_url
from .base import BaseJsonClient, RequestSpec


@dataclass(frozen=True)
class OpenAiClient(BaseJsonClient):
    base_url: str
    api_key: str
    model: str = "gpt-4o-mini"
    default_timeout_ms: int = 300_000

    @property
    def provider(self) -> str:
        return "openai"

    def _request_candidates(self, *, messages: list[dict[str, str]], temperature: float) -> list[RequestSpec]:
        url = f"{normalize_openai_base_url(self.base_url)}/chat/completions"
        base_body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
        }
        candidate_bodies = [
            {**base_body, "response_format": {"type": "json_object"}},
            base_body,
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        return [RequestSpec(url=url, headers=headers, body=body, retries=3) for body in candidate_bodies]

    def _extract_content(self, response_obj: dict[str, Any]) -> str:
        choices = response_obj.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI response missing choices[0]")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        return str(message.get("content") if isinstance(message, dict) else "")
