
from __future__ import annotations
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from core.sources.journals.journal_config import (
    CELL_FAMILY,
    ELIFE_FAMILY,
    NATURE_FAMILY,
    OTHER_FAMILY,
    PMC_FAMILY,
    PLOS_FAMILY,
    SCIENCE_FAMILY,
    JournalFamily,
)
from core.sources.journals.models import PaperRecord
from .config import CrawlConfig
from .discovery import ArticleDiscovery
from .downloader import FigureDownloader
from .extractor import ContentExtractor
from .http_client import AsyncHTTPClient

logger = logging.getLogger("science_crawler")


@dataclass
class CrawlStats:
    """Accumulated statistics for a crawl_journals run."""

    total_papers: int = 0
    total_figures: int = 0
    total_data_sources: int = 0
    by_family: Dict[str, int] = field(default_factory=dict)
    errors: int = 0
    skipped: int = 0
    start_time: str = ""
    end_time: str = ""


def _paper_key(paper: Any = None) -> str:
    """Return a unique deduplication key for a paper record.

    Tries DOI first, then URL, PMC ID, PMID, and finally the title.
    """
    doi = str(getattr(paper, "doi", "") or "").strip()
    if doi:
        return doi

    url = str(getattr(paper, "url", "") or "").strip()
    if url:
        return url

    pmc_id = str(getattr(paper, "pmc_id", "") or "").strip()
    if pmc_id:
        return f"pmc:{pmc_id}"

    pmid = str(getattr(paper, "pmid", "") or "").strip()
    if pmid:
        return f"pmid:{pmid}"

    title = str(getattr(paper, "title", "") or "").strip()
    return title


def _family_map() -> Dict[str, JournalFamily]:
    """Return a mapping of human-readable family name to its JournalFamily config."""
    return {
        "Nature": NATURE_FAMILY,
        "Science": SCIENCE_FAMILY,
        "Cell": CELL_FAMILY,
        "PLOS": PLOS_FAMILY,
        "eLife": ELIFE_FAMILY,
        "PMC": PMC_FAMILY,
        "Other": OTHER_FAMILY,
    }


def _split_target(remaining: int = 0, buckets: int = 1) -> int:
    """Divide *remaining* evenly across *buckets*, rounding up, minimum 1."""
    if remaining <= 0:
        return 0
    buckets = max(1, int(buckets))
    return max(1, (int(remaining) + buckets - 1) // buckets)


async def crawl_journals(
    *,
    config: CrawlConfig,
    on_paper: Callable[[PaperRecord], Awaitable[None] | None],
) -> CrawlStats:
    """Crawl papers from configured journal families and invoke a callback per paper.

    This is a refactor-friendly wrapper around the original Benchmark prototype:
    it performs discovery + enrichment (figures/data links) and (optionally)
    downloads figure images.

    It does **not** write metadata JSONL/indexes itself; the caller owns persistence.
    """

    stats = CrawlStats(start_time=datetime.now().isoformat())
    seen_keys: set[str] = set()

    client = AsyncHTTPClient(config)
    discovery = ArticleDiscovery(client, config)
    extractor = ContentExtractor(client, config)
    downloader = FigureDownloader(client, config)

    families = _family_map()
    enabled_families = getattr(config, "families", None) or list(families.keys())

    try:
        for family_name in enabled_families:
            family = families.get(family_name)
            if family is None:
                logger.warning("Unknown journal family '%s', skipping.", family_name)
                continue

            global_left = max(0, getattr(config, "max_papers", 5000) - stats.total_papers)
            if global_left <= 0:
                logger.info("Global paper limit reached; stopping crawl.")
                break

            family_quota = getattr(family, "max_papers", None) or global_left
            quota = min(family_quota, global_left)
            collected = 0

            logger.info(
                "Crawling family '%s' (quota=%d, global_left=%d)",
                family_name,
                quota,
                global_left,
            )

            # --- Discovery phase ---
            papers: List[PaperRecord] = []
            try:
                journals = getattr(family, "journals", [])
                enrichment_type = getattr(family, "enrichment_type", "pmc")
                per_journal = _split_target(quota, len(journals)) if journals else quota

                if enrichment_type == "nature" or family_name == "Nature":
                    for jinfo in journals:
                        issn = jinfo.get("issn", "") if isinstance(jinfo, dict) else getattr(jinfo, "issn", "")
                        discovered = await discovery.discover_springer_articles(
                            issn=issn,
                            max_results=per_journal,
                        )
                        papers.extend(discovered)
                elif enrichment_type == "plos" or family_name == "PLOS":
                    for jinfo in journals:
                        slug = jinfo.get("slug", "") if isinstance(jinfo, dict) else getattr(jinfo, "slug", "")
                        discovered = await discovery.discover_plos_articles(
                            journal_slug=slug,
                            max_results=per_journal,
                        )
                        papers.extend(discovered)
                elif enrichment_type == "elife" or family_name == "eLife":
                    discovered = await discovery.discover_elife_articles(
                        max_results=quota,
                    )
                    papers.extend(discovered)
                else:
                    # PMC-based discovery (Science, Cell, PMC, Other)
                    for jinfo in journals:
                        issn = jinfo.get("issn", "") if isinstance(jinfo, dict) else getattr(jinfo, "issn", "")
                        name = jinfo.get("name", "") if isinstance(jinfo, dict) else getattr(jinfo, "name", "")
                        discovered = await discovery.discover_pmc_articles(
                            issn=issn,
                            journal_name=name,
                            max_results=per_journal,
                        )
                        papers.extend(discovered)
            except Exception:
                logger.exception("Discovery failed for family '%s'.", family_name)
                stats.errors += 1
                continue

            logger.info(
                "Family '%s': discovered %d candidate papers.", family_name, len(papers)
            )

            # --- Enrichment + callback phase ---
            for paper in papers:
                if collected >= quota:
                    break
                if stats.total_papers >= getattr(config, "max_papers", 5000):
                    break

                key = _paper_key(paper)
                if not key or key in seen_keys:
                    stats.skipped += 1
                    continue
                seen_keys.add(key)

                try:
                    enrichment_type = getattr(family, "enrichment_type", "pmc")
                    if enrichment_type == "nature":
                        await extractor.enrich_nature_paper(paper)
                    elif enrichment_type == "plos":
                        await extractor.enrich_plos_paper(paper)
                    elif enrichment_type == "elife":
                        await extractor.enrich_elife_paper(paper)
                    elif enrichment_type == "pmc":
                        pmc_id = getattr(paper, "pmc_id", "") or ""
                        if pmc_id:
                            await extractor.enrich_paper_via_pmc(
                                pmc_ids=[pmc_id],
                                family_name=family_name,
                            )
                    else:
                        await extractor.enrich_generic_paper(paper)

                    # Download figures if configured
                    if getattr(config, "download_figures", False):
                        await downloader.download_paper_figures(paper)

                except Exception:
                    logger.exception(
                        "Error processing paper '%s' in family '%s'.",
                        key,
                        family_name,
                    )
                    stats.errors += 1
                    continue

                # Invoke caller-supplied callback
                try:
                    result = on_paper(paper)
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        await result
                except Exception:
                    logger.exception("on_paper callback failed for '%s'.", key)
                    stats.errors += 1
                    continue

                # Update stats
                collected += 1
                stats.total_papers += 1
                stats.total_figures += len(getattr(paper, "figures", []) or [])
                stats.total_data_sources += len(getattr(paper, "data_sources", []) or [])

            stats.by_family[family_name] = collected
            logger.info(
                "Family '%s': collected %d papers.", family_name, collected
            )

    finally:
        await client.close()

    stats.end_time = datetime.now().isoformat()
    logger.info(
        "Crawl complete: %d papers, %d figures, %d data sources, %d errors, %d skipped.",
        stats.total_papers,
        stats.total_figures,
        stats.total_data_sources,
        stats.errors,
        stats.skipped,
    )
    return stats
