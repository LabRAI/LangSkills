from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class LlmClient(Protocol):
    provider: str
    model: str

    def chat_json(
        self,
        *,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]: ...
