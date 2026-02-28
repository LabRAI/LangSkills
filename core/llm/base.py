from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

from ..utils.http import fetch_with_retries, try_parse_json_object


@dataclass(frozen=True)
class RequestSpec:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    retries: int = 3
    method: str = "POST"
    accept: str = "application/json"


class BaseJsonClient(ABC):
    provider: str
    model: str
    default_timeout_ms: int = 60_000
    max_preview_chars: int = 400

    def _normalize_messages(self, messages: Iterable[Any]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for m in messages:
            if hasattr(m, "to_dict") and callable(getattr(m, "to_dict")):
                try:
                    d = m.to_dict()
                    if isinstance(d, dict):
                        out.append({"role": str(d.get("role") or ""), "content": str(d.get("content") or "")})
                        continue
                except Exception:
                    pass
            if isinstance(m, dict):
                out.append({"role": str(m.get("role") or ""), "content": str(m.get("content") or "")})
                continue
            out.append({"role": "user", "content": str(m)})
        return out

    def _local_response(
        self,
        *,
        messages: list[Any],
        temperature: float,
        timeout_ms: int,
    ) -> dict[str, Any] | None:
        return None

    @abstractmethod
    def _request_candidates(self, *, messages: list[dict[str, str]], temperature: float) -> list[RequestSpec]:
        raise NotImplementedError

    @abstractmethod
    def _extract_content(self, response_obj: dict[str, Any]) -> str:
        raise NotImplementedError

    def chat_json(
        self,
        *,
        messages: list[Any],
        temperature: float = 0.2,
        timeout_ms: int | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        effective_timeout = int(timeout_ms or self.default_timeout_ms)

        local = self._local_response(messages=messages, temperature=temperature, timeout_ms=effective_timeout)
        if local is not None:
            return local

        msg_dicts = self._normalize_messages(messages)
        candidates = self._request_candidates(messages=msg_dicts, temperature=temperature)
        if not candidates:
            raise RuntimeError(f"{self.provider} request failed: no request candidates")

        if max_tokens:
            for spec in candidates:
                spec.body.setdefault("max_tokens", max_tokens)

        last_err: Exception | None = None
        for spec in candidates:
            try:
                resp = fetch_with_retries(
                    spec.url,
                    method=spec.method,
                    timeout_ms=effective_timeout,
                    retries=int(spec.retries),
                    accept=spec.accept,
                    headers=spec.headers,
                    body=json.dumps(spec.body),
                )
                parsed = try_parse_json_object(resp.text)
                if not isinstance(parsed, dict):
                    raise RuntimeError(f"Invalid {self.provider} response JSON: {spec.url}")
                content = self._extract_content(parsed)
                obj = try_parse_json_object(str(content or ""))
                if not isinstance(obj, dict):
                    preview = str(content or "")[: self.max_preview_chars]
                    raise RuntimeError(f"Model did not return a JSON object. Preview: {preview}")
                return obj
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"{self.provider} request failed") from last_err
