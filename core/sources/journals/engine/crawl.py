Unsupported Node type: 12
Unsupported opcode: MAKE_CELL (225)
# Source Generated with Decompyle++
# File: crawl.pyc (Python 3.12)

from __future__ import annotations
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from core.sources.journals.journal_config import CELL_FAMILY, ELIFE_FAMILY, NATURE_FAMILY, OTHER_FAMILY, PMC_FAMILY, PLOS_FAMILY, SCIENCE_FAMILY, JournalFamily
from core.sources.journals.models import PaperRecord
from .config import CrawlConfig
from .discovery import ArticleDiscovery
from .downloader import FigureDownloader
from .extractor import ContentExtractor
from .http_client import AsyncHTTPClient
CrawlStats = <NODE:12>()

def _paper_key(paper = None):
    if not getattr(paper, 'doi', ''):
        getattr(paper, 'doi', '')
    doi = str('').strip()
    if doi:
        return doi
    if not getattr(paper, 'url', ''):
        getattr(paper, 'url', '')
    url = None('').strip()
    if url:
        return url
    if not getattr(paper, 'pmc_id', ''):
        getattr(paper, 'pmc_id', '')
    pmc_id = None('').strip()
    if pmc_id:
        return f'''pmc:{pmc_id}'''
    if not getattr(paper, 'pmid', ''):
        getattr(paper, 'pmid', '')
    pmid = None('').strip()
    if pmid:
        return f'''pmid:{pmid}'''
    if not getattr(paper, 'title', ''):
        getattr(paper, 'title', '')
    title = None('').strip()
    return title


def _family_map():
    return {
        'Nature': NATURE_FAMILY,
        'Science': SCIENCE_FAMILY,
        'Cell': CELL_FAMILY,
        'PLOS': PLOS_FAMILY,
        'eLife': ELIFE_FAMILY,
        'PMC': PMC_FAMILY,
        'Other': OTHER_FAMILY }


def _split_target(remaining = None, buckets = None):
    if remaining <= 0:
        return 0
    buckets = max(1, int(buckets))
    return max(1, (int(remaining) + buckets - 1) // buckets)


async def crawl_journals(*, config, on_paper):
    '''Crawl papers from configured journal families and invoke a callback per paper.

    This is a refactor-friendly wrapper around the original Benchmark prototype:
    it performs discovery + enrichment (figures/data links) and (optionally)
    downloads figure images.

    It does **not** write metadata JSONL/indexes itself; the caller owns persistence.
    '''
    pass
# WARNING: Decompyle incomplete

