
'''Main crawl orchestrator.'''
import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Set
from core.sources.journals.models import PaperRecord
from core.sources.journals.journal_config import JournalFamily, NATURE_FAMILY, SCIENCE_FAMILY, CELL_FAMILY, PLOS_FAMILY, ELIFE_FAMILY, PMC_FAMILY, OTHER_FAMILY
from .config import CrawlConfig
from .http_client import AsyncHTTPClient
from .discovery import ArticleDiscovery
from .extractor import ContentExtractor
from .downloader import FigureDownloader
from .storage import DataStorage
logger = logging.getLogger('science_crawler')

class CrawlOrchestrator:
    '''Main orchestrator that coordinates discovery, extraction, download, and storage.'''

    def __init__(self, config: CrawlConfig):
        self.config = config
        self.client = AsyncHTTPClient(config)
        self.discovery = ArticleDiscovery(self.client, config)
        self.extractor = ContentExtractor(self.client, config)
        self.downloader = FigureDownloader(self.client, config)
        self.storage = DataStorage(config)
        self.seen_dois: Set[str] = set()
        self.stats = {
            'total_papers': 0,
            'total_figures': 0,
            'total_data_sources': 0,
            'by_family': {},
            'start_time': '',
            'end_time': ''}

    async def run(self):
        '''Run the full crawl pipeline.'''
        self.stats['start_time'] = datetime.now().isoformat()
        # Resume support: load already-crawled DOIs so we skip them.
        self.seen_dois = self.storage.get_existing_dois()
        logger.info('Resuming with %d already-crawled DOIs', len(self.seen_dois))

        families = {
            'Nature': NATURE_FAMILY,
            'Science': SCIENCE_FAMILY,
            'Cell': CELL_FAMILY,
            'PLOS': PLOS_FAMILY,
            'eLife': ELIFE_FAMILY,
            'PMC': PMC_FAMILY,
            'Other': OTHER_FAMILY}

        try:
            for name, family in families.items():
                if self.stats['total_papers'] >= self.config.max_papers:
                    logger.info('Global paper limit reached (%d). Stopping.', self.config.max_papers)
                    break
                quota = _split_target(
                    self.config.max_papers - self.stats['total_papers'],
                    len(families))
                logger.info('Crawling family %s (quota=%d)', name, quota)
                await self._crawl_family(family, quota)
        finally:
            self.stats['end_time'] = datetime.now().isoformat()
            self.storage.save_summary(self.stats)
            await self.client.close()

        logger.info(
            'Crawl complete: %d papers, %d figures, %d data sources',
            self.stats['total_papers'],
            self.stats['total_figures'],
            self.stats['total_data_sources'])

    def _remaining_slots(self, collected: int, quota: int) -> int:
        '''How many more papers can be processed in current family and globally.'''
        family_left = max(0, quota - collected)
        global_left = max(0, self.config.max_papers - self.stats['total_papers'])
        return min(family_left, global_left)

    def _build_tasks(self, papers: List[PaperRecord], enrichment_type: str, budget: int) -> List:
        '''Build process tasks capped by current paper budget.'''
        tasks = []
        for p in papers:
            if budget <= 0:
                return tasks
            if not p.doi:
                continue
            if p.doi in self.seen_dois:
                continue
            tasks.append(self._process_paper(p, enrichment_type))
            budget -= 1
        return tasks

    async def _crawl_family(self, family: JournalFamily, quota: int):
        '''Crawl a single journal family.'''
        family_name = getattr(family, 'name', 'Unknown')
        collected = 0
        self.stats['by_family'].setdefault(family_name, {
            'papers': 0, 'figures': 0, 'data_sources': 0})

        enrichment_type = getattr(family, 'enrichment_type', 'generic')

        # Discovery phase: gather candidate papers from the family's journals.
        papers: List[PaperRecord] = []
        try:
            journals = getattr(family, 'journals', [])
            remaining = self._remaining_slots(collected, quota)
            per_journal = _split_target(remaining, len(journals)) if journals else remaining

            for journal in journals:
                issn = getattr(journal, 'issn', '')
                name = getattr(journal, 'name', '')
                slug = getattr(journal, 'slug', '')

                if enrichment_type == 'nature':
                    discovered = await self.discovery.discover_springer_articles(
                        issn=issn, max_results=per_journal)
                elif enrichment_type == 'plos':
                    discovered = await self.discovery.discover_plos_articles(
                        journal_slug=slug, max_results=per_journal)
                elif enrichment_type == 'elife':
                    discovered = await self.discovery.discover_elife_articles(
                        max_results=per_journal)
                elif enrichment_type == 'pmc':
                    discovered = await self.discovery.discover_pmc_articles(
                        issn=issn, journal_name=name, max_results=per_journal)
                else:
                    discovered = await self.discovery.discover_pmc_articles(
                        issn=issn, journal_name=name, max_results=per_journal)
                papers.extend(discovered)
        except Exception:
            logger.exception('Discovery failed for family %s', family_name)

        # Enrichment + download phase: process each paper concurrently.
        budget = self._remaining_slots(collected, quota)
        tasks = self._build_tasks(papers, enrichment_type, budget)
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning('Paper processing failed: %s', result)
                elif isinstance(result, PaperRecord):
                    collected += 1

        logger.info('Family %s: collected %d papers', family_name, collected)

    async def _process_paper(self, paper: PaperRecord, enrichment_type: str) -> PaperRecord:
        '''Process a single paper: enrich, download figures, save.'''
        try:
            # Enrichment: extract figures, data links, and fulltext sections.
            if enrichment_type == 'nature':
                paper = await self.extractor.enrich_nature_paper(paper)
            elif enrichment_type == 'plos':
                paper = await self.extractor.enrich_plos_paper(paper)
            elif enrichment_type == 'elife':
                paper = await self.extractor.enrich_elife_paper(paper)
            elif enrichment_type == 'pmc':
                pmc_id = getattr(paper, 'pmc_id', '')
                if pmc_id:
                    enriched = await self.extractor.enrich_paper_via_pmc(
                        [pmc_id], family_name=getattr(paper, 'journal_family', ''))
                    if enriched:
                        paper = enriched[0]
            else:
                paper = await self.extractor.enrich_generic_paper(paper)

            # Download figures if configured.
            if self.config.download_figures:
                await self.downloader.download_paper_figures(paper)

            # Persist.
            self.storage.save_paper(paper)
            self.seen_dois.add(paper.doi)

            # Update stats.
            n_figs = len(getattr(paper, 'figures', None) or [])
            n_data = len(getattr(paper, 'data_sources', None) or [])
            self.stats['total_papers'] += 1
            self.stats['total_figures'] += n_figs
            self.stats['total_data_sources'] += n_data

            family_name = getattr(paper, 'journal_family', 'Unknown')
            fam_stats = self.stats['by_family'].setdefault(
                family_name, {'papers': 0, 'figures': 0, 'data_sources': 0})
            fam_stats['papers'] += 1
            fam_stats['figures'] += n_figs
            fam_stats['data_sources'] += n_data

            logger.info(
                'Processed %s — %d figures, %d data sources',
                paper.doi, n_figs, n_data)
            return paper

        except Exception:
            logger.exception('Failed to process paper %s', getattr(paper, 'doi', '?'))
            raise


def _split_target(remaining: int, buckets: int) -> int:
    '''Divide *remaining* items across *buckets* groups, rounding up (min 1).'''
    if remaining <= 0:
        return 0
    buckets = max(1, int(buckets))
    return max(1, (int(remaining) + buckets - 1) // buckets)
