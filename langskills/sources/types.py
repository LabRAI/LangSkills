from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceInput:
    source_type: str
    url: str
    title: str
    text: str
    fetched_at: str
    extra: dict[str, Any]


@dataclass(frozen=True)
class FetchResult:
    raw_html: str
    extracted_text: str
    final_url: str = ""
    title: str = ""
    platform: str = ""
    used_playwright: bool = False
    debug: dict[str, Any] = field(default_factory=dict)
