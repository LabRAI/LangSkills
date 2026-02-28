from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..env import normalize_ollama_base_url
from .base import BaseJsonClient, RequestSpec


@dataclass(frozen=True)
class OllamaClient(BaseJsonClient):
    base_url: str
    model: str

    @property
    def provider(self) -> str:
        return "ollama"

    def _request_candidates(self, *, messages: list[dict[str, str]], temperature: float) -> list[RequestSpec]:
        url = f"{normalize_ollama_base_url(self.base_url)}/api/chat"
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": float(temperature)},
        }
        return [RequestSpec(url=url, headers={"Content-Type": "application/json"}, body=body, retries=1)]

    def _extract_content(self, response_obj: dict[str, Any]) -> str:
        msg = response_obj.get("message") if isinstance(response_obj.get("message"), dict) else {}
        return str(msg.get("content") if isinstance(msg, dict) else "")
