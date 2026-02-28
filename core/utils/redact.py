from __future__ import annotations

import re
from typing import Any


SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{8,}|tvly-[a-z0-9]{8,}|ghp_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|bearer\\s+[a-z0-9._-]{8,})"
)
SENSITIVE_KEY_ASSIGN_RE = re.compile(
    r"(?i)\\b(OPENAI_API_KEY|TAVILY_API_KEY|GITHUB_TOKEN|OLLAMA_API_KEY|API_KEY|TOKEN|SECRET|PASSWORD)\\b\\s*[:=]\\s*\\S+"
)
URL_SCHEME_RE = re.compile(r"(?i)\\b(?:https?://|file://)\\S+")


def redact_text(text: str, *, redact_urls: bool) -> str:
    """
    Best-effort redaction for logs/prompts/traces.
    - Always redacts common token formats (OpenAI/Tavily/GitHub/Bearer).
    - Optionally redacts URLs (disabled by default because it harms auditability).
    """
    s = str(text or "")
    s = SENSITIVE_VALUE_RE.sub("<redacted>", s)
    s = SENSITIVE_KEY_ASSIGN_RE.sub(r"\\1=<redacted>", s)
    if redact_urls:
        s = URL_SCHEME_RE.sub("<redacted_url>", s)
    return s


def redact_obj(obj: Any, *, redact_urls: bool) -> Any:
    """
    Recursively redact strings inside JSON-like objects (dict/list/scalars).
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return redact_text(obj, redact_urls=redact_urls)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [redact_obj(x, redact_urls=redact_urls) for x in obj]
    if isinstance(obj, dict):
        return {str(k): redact_obj(v, redact_urls=redact_urls) for k, v in obj.items()}
    return redact_text(str(obj), redact_urls=redact_urls)

