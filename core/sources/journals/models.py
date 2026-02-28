"""
Data models for journal article records, figures, and data sources.

These are simple data classes used across all journal parsers and the engine.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FigureInfo:
    """Metadata for a single figure extracted from a journal article."""
    figure_id: str = ""
    caption: str = ""
    full_size_url: str = ""
    thumbnail_url: str = ""
    figure_type: str = "main"  # main, extended, supplementary, table


@dataclass
class DataSource:
    """An external data repository reference found in an article."""
    repository: str = ""
    accession: str = ""
    url: str = ""


@dataclass
class PaperRecord:
    """Metadata and extracted content for a single journal article."""
    doi: str = ""
    title: str = ""
    journal: str = ""
    journal_family: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    pub_date: str = ""
    url: str = ""
    figures: List[FigureInfo] = field(default_factory=list)
    data_sources: List[DataSource] = field(default_factory=list)
    is_open_access: bool = False
    pmc_id: str = ""
    pmid: str = ""
    raw_xml: str = ""
    fulltext_sections: Optional[dict] = None
