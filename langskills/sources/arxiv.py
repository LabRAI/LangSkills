from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, List
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from ..config import canonicalize_source_url
from ..sources.types import FetchResult
from ..sources.types import SourceInput
from ..utils.time import utc_now_iso_z
from ..utils.urls import ARXIV_ABS_BASE, ARXIV_ABS_PATH


def _fetch_feed(query: str, max_results: int = 5, *, timeout_sec: float = 20.0) -> str:
    url = f"http://export.arxiv.org/api/query?search_query={quote(query)}&start=0&max_results={int(max_results)}"
    with urlopen(url, timeout=float(timeout_sec)) as resp:  # nosec - arxiv public API
        return resp.read().decode("utf-8", errors="replace")


def search_arxiv(topic: str, max_results: int = 5) -> list[dict]:
    """
    Minimal arXiv search via Atom feed. Returns list of dict entries.
    """
    feed_xml = _fetch_feed(f"all:{topic}", max_results=max_results)
    root = ET.fromstring(feed_xml)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entries: list[dict] = []
    for e in root.findall("atom:entry", ns):
        arxiv_id = ""
        id_tag = e.find("atom:id", ns)
        if id_tag is not None and id_tag.text:
            m = re.search(rf"{re.escape(ARXIV_ABS_PATH)}([^/]+)$", id_tag.text.strip())
            if m:
                arxiv_id = m.group(1)
        title = (e.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (e.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        comment = (e.findtext("arxiv:comment", default="", namespaces=ns) or "").strip()
        authors = [a.text.strip() for a in e.findall("atom:author/atom:name", ns) if a.text]
        categories = [c.attrib.get("term", "").strip() for c in e.findall("atom:category", ns)]
        categories = [c for c in categories if c]
        pdf_url = ""
        for link in e.findall("atom:link", ns):
            if link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        primary_url = f"{ARXIV_ABS_BASE}{arxiv_id}" if arxiv_id else ""
        entries.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "comment": comment,
                "authors": authors,
                "categories": categories,
                "pdf_url": pdf_url,
                "primary_url": primary_url,
            }
        )
    return entries


def build_source_input_from_entry(entry: dict, *, skill_kind: str = "paper_writing") -> SourceInput:
    url_raw = entry.get("primary_url") or ""
    url = canonicalize_source_url(url_raw) or url_raw
    abstract = entry.get("summary") or ""
    comment = str(entry.get("comment") or "").strip()
    comment_block = f"\n\nCOMMENT:\n{comment}" if comment else ""
    text = (
        f"TITLE: {entry.get('title','')}\nAUTHORS: {', '.join(entry.get('authors') or [])}\n\nABSTRACT:\n{abstract}"
        f"{comment_block}"
    )
    tags = entry.get("categories") or []
    return SourceInput(
        source_type="arxiv",
        url=url,
        title=entry.get("title") or "",
        text=text,
        fetched_at=utc_now_iso_z(),
        extra={
            "skill_kind": skill_kind,
            "language": "en",
            "arxiv_id": entry.get("arxiv_id") or "",
            "pdf_url": entry.get("pdf_url") or "",
            "comment": comment,
            "authors": entry.get("authors") or [],
            "tags": tags,
        },
    )


def discover_arxiv_sources(topic: str, *, max_results: int = 5, skill_kinds: List[str] | None = None) -> list[SourceInput]:
    kinds = skill_kinds or ["paper_writing", "paper_writeup", "experiment_design"]
    entries = search_arxiv(topic, max_results=max_results)
    out: list[SourceInput] = []
    for entry in entries:
        for kind in kinds:
            out.append(build_source_input_from_entry(entry, skill_kind=kind))
    return out


def parse_arxiv_id(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""

    # Direct id input.
    if re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", s):
        return s
    if re.match(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?$", s, flags=re.IGNORECASE):
        return s

    # URL forms.
    try:
        parts = urlsplit(s)
    except Exception:
        return ""
    host = str(parts.hostname or "").strip().lower()
    if host not in {"arxiv.org", "www.arxiv.org"}:
        return ""
    path = str(parts.path or "")
    m = re.search(r"^/abs/([^/?#]+)", path)
    if m:
        return m.group(1)
    m = re.search(r"^/pdf/([^/?#]+)", path)
    if m:
        return re.sub(r"\.pdf$", "", m.group(1), flags=re.IGNORECASE)
    return ""


def _parse_arxiv_entry(feed_xml: str) -> dict[str, Any] | None:
    try:
        root = ET.fromstring(feed_xml)
    except Exception:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return None

    arxiv_id = ""
    id_tag = entry.find("atom:id", ns)
    if id_tag is not None and id_tag.text:
        m = re.search(rf"{re.escape(ARXIV_ABS_PATH)}([^/]+)$", id_tag.text.strip())
        if m:
            arxiv_id = m.group(1)

    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
    summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
    comment = (entry.findtext("arxiv:comment", default="", namespaces=ns) or "").strip()
    authors = [a.text.strip() for a in entry.findall("atom:author/atom:name", ns) if a.text]
    categories = [c.attrib.get("term", "").strip() for c in entry.findall("atom:category", ns)]
    categories = [c for c in categories if c]
    pdf_url = ""
    for link in entry.findall("atom:link", ns):
        if link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break
    primary_url = f"{ARXIV_ABS_BASE}{arxiv_id}" if arxiv_id else ""
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "summary": summary,
        "comment": comment,
        "authors": authors,
        "categories": categories,
        "pdf_url": pdf_url,
        "primary_url": primary_url,
    }


def fetch_arxiv_text(
    url_or_id: str,
    *,
    timeout_ms: int = 20_000,
    info: dict[str, Any] | None = None,
) -> FetchResult:
    """
    Fetch arXiv metadata (title + abstract) via the public API.

    This is intentionally lightweight and stable (no PDF parsing).
    """
    raw = str(url_or_id or "").strip()
    if not raw:
        return FetchResult(raw_html="", extracted_text="", final_url="", platform="arxiv", used_playwright=False)

    arxiv_id = parse_arxiv_id(raw)
    if not arxiv_id:
        from .webpage import fetch_webpage_text

        if info is not None:
            info["status"] = "fallback_webpage"
        return fetch_webpage_text(raw, timeout_ms=timeout_ms, retries=1)

    timeout_sec = max(1.0, min(180.0, float(timeout_ms) / 1000.0))
    url = f"http://export.arxiv.org/api/query?id_list={quote(arxiv_id)}"
    with urlopen(url, timeout=timeout_sec) as resp:  # nosec - arxiv public API
        feed_xml = resp.read().decode("utf-8", errors="replace")

    entry = _parse_arxiv_entry(feed_xml) or {}
    src = canonicalize_source_url(str(entry.get("primary_url") or "")) or str(entry.get("primary_url") or "")
    if not src:
        src = canonicalize_source_url(f"{ARXIV_ABS_BASE}{arxiv_id}") or f"{ARXIV_ABS_BASE}{arxiv_id}"

    title = str(entry.get("title") or "").strip()
    summary = str(entry.get("summary") or "").strip()
    comment = str(entry.get("comment") or "").strip()
    authors = entry.get("authors") if isinstance(entry.get("authors"), list) else []
    comment_block = f"\n\nCOMMENT:\n{comment}" if comment else ""
    text = (
        f"TITLE: {title}\nAUTHORS: {', '.join([str(a) for a in authors if str(a).strip()])}\n\nABSTRACT:\n{summary}"
        f"{comment_block}"
    )

    debug: dict[str, Any] = {}
    if info is not None:
        info["arxiv_id"] = arxiv_id
        info["pdf_url"] = str(entry.get("pdf_url") or "")
        info["categories"] = entry.get("categories") if isinstance(entry.get("categories"), list) else []
        info["comment"] = comment
        debug["arxiv"] = info

    return FetchResult(
        raw_html=feed_xml,
        extracted_text=text,
        final_url=src,
        title=title,
        platform="arxiv",
        used_playwright=False,
        debug=debug,
    )
