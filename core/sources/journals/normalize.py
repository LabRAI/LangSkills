"""Normalization helpers for journal paper records.

Extracts primary URLs, plain text, and raw JSON from PaperRecord objects.
"""
from __future__ import annotations

import json
from typing import Any

from .models import PaperRecord


def paper_primary_url(paper: PaperRecord) -> str:
    """Return the best URL for a paper (DOI link preferred)."""
    doi = str(getattr(paper, "doi", "") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    url = str(getattr(paper, "url", "") or "").strip()
    if url:
        return url
    pmc_id = str(getattr(paper, "pmc_id", "") or "").strip()
    if pmc_id:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
    return ""


def paper_to_extracted_text(paper: PaperRecord, *, max_chars: int = 12000) -> str:
    """Flatten a PaperRecord into a single plain-text string for LLM consumption."""
    parts: list[str] = []

    title = str(getattr(paper, "title", "") or "").strip()
    if title:
        parts.append(f"Title: {title}")

    journal = str(getattr(paper, "journal", "") or "").strip()
    if journal:
        parts.append(f"Journal: {journal}")

    doi = str(getattr(paper, "doi", "") or "").strip()
    if doi:
        parts.append(f"DOI: {doi}")

    abstract = str(getattr(paper, "abstract", "") or "").strip()
    if abstract:
        parts.append(f"\nAbstract:\n{abstract}")

    sections = getattr(paper, "fulltext_sections", None) or {}
    for key in ("introduction", "methods", "results", "discussion"):
        text = str(sections.get(key, "") or "").strip()
        if text:
            parts.append(f"\n{key.title()}:\n{text}")

    figures = getattr(paper, "figures", []) or []
    if figures:
        fig_lines = []
        for fig in figures[:20]:
            fid = str(getattr(fig, "figure_id", "") or "")
            cap = str(getattr(fig, "caption", "") or "").strip()
            if cap:
                fig_lines.append(f"  - {fid}: {cap[:200]}")
        if fig_lines:
            parts.append("\nFigures:\n" + "\n".join(fig_lines))

    data_sources = getattr(paper, "data_sources", []) or []
    if data_sources:
        ds_lines = []
        for ds in data_sources[:20]:
            repo = str(getattr(ds, "repository", "") or "")
            acc = str(getattr(ds, "accession", "") or "")
            ds_lines.append(f"  - {repo}: {acc}")
        if ds_lines:
            parts.append("\nData Sources:\n" + "\n".join(ds_lines))

    text = "\n".join(parts)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text


def paper_to_raw_json(paper: PaperRecord) -> dict[str, Any]:
    """Convert a PaperRecord to a JSON-serializable dict."""
    figures = []
    for fig in (getattr(paper, "figures", []) or []):
        figures.append({
            "figure_id": str(getattr(fig, "figure_id", "") or ""),
            "caption": str(getattr(fig, "caption", "") or ""),
            "full_size_url": str(getattr(fig, "full_size_url", "") or ""),
            "thumbnail_url": str(getattr(fig, "thumbnail_url", "") or ""),
            "figure_type": str(getattr(fig, "figure_type", "") or ""),
        })

    data_sources = []
    for ds in (getattr(paper, "data_sources", []) or []):
        data_sources.append({
            "repository": str(getattr(ds, "repository", "") or ""),
            "accession": str(getattr(ds, "accession", "") or ""),
            "url": str(getattr(ds, "url", "") or ""),
        })

    return {
        "doi": str(getattr(paper, "doi", "") or ""),
        "title": str(getattr(paper, "title", "") or ""),
        "journal": str(getattr(paper, "journal", "") or ""),
        "journal_family": str(getattr(paper, "journal_family", "") or ""),
        "authors": list(getattr(paper, "authors", []) or []),
        "abstract": str(getattr(paper, "abstract", "") or ""),
        "pub_date": str(getattr(paper, "pub_date", "") or ""),
        "url": str(getattr(paper, "url", "") or ""),
        "pmc_id": str(getattr(paper, "pmc_id", "") or ""),
        "is_open_access": bool(getattr(paper, "is_open_access", False)),
        "figures": figures,
        "data_sources": data_sources,
        "fulltext_sections": dict(getattr(paper, "fulltext_sections", {}) or {}),
    }
