
'''Content extraction: fetch article HTML/XML and extract figures + data links.'''
import re
import logging
import xml.etree.ElementTree as ET
from typing import List
from core.sources.journals.models import PaperRecord
from core.sources.journals.parsers.pmc_parser import build_efetch_url, parse_article_xml
from core.sources.journals.parsers.nature_parser import parse_nature_article_html
from core.sources.journals.parsers.plos_parser import extract_plos_figures_from_html, extract_plos_data_from_html, _doi_to_plos_slug
from core.sources.journals.parsers.elife_parser import build_elife_article_url
from core.sources.journals.parsers.html_parser import extract_figures_bs4, extract_data_availability_bs4, extract_fulltext_sections_bs4
from .config import CrawlConfig
from .http_client import AsyncHTTPClient
logger = logging.getLogger('science_crawler')


class ContentExtractor:
    '''Fetch article HTML/XML and extract figures + data links.'''

    def __init__(self, client: AsyncHTTPClient, config: CrawlConfig):
        self.client = client
        self.config = config

    async def enrich_paper_via_pmc(self, pmc_ids: List[str], family_name: str = '') -> List[PaperRecord]:
        '''Fetch full XML from PMC and parse into PaperRecords with figures and data.'''
        if not pmc_ids:
            return []
        api_key = getattr(self.config, 'ncbi_api_key', '')
        url = build_efetch_url(pmc_ids, api_key=api_key)
        try:
            xml_text = await self.client.get_text(url)
            if not xml_text:
                return []
            root = ET.fromstring(xml_text)
            papers = []
            for article_elem in root.iter('article'):
                paper = parse_article_xml(article_elem)
                if paper is not None:
                    if family_name:
                        paper.journal_family = family_name
                    papers.append(paper)
            return papers
        except Exception as exc:
            logger.warning('PMC efetch failed for %d IDs: %s', len(pmc_ids), exc)
            return []

    async def enrich_nature_paper(self, paper: PaperRecord) -> None:
        '''Fetch Nature article HTML and extract figures + data + fulltext sections.'''
        if not paper.url:
            return
        try:
            html = await self.client.get_text(paper.url)
            if not html:
                return
            figures, data_sources = parse_nature_article_html(html, doi=paper.doi)
            if figures:
                paper.figures = figures
            if data_sources:
                paper.data_sources = data_sources
            self._merge_html_sections(paper, html)
        except Exception as exc:
            logger.warning('Nature enrichment failed for %s: %s', paper.doi, exc)

    async def enrich_plos_paper(self, paper: PaperRecord) -> None:
        '''Enrich PLOS paper with figures, data, and fulltext sections from article HTML.'''
        if not paper.doi:
            return
        slug = _doi_to_plos_slug(paper.doi)
        article_url = f'https://journals.plos.org/{slug}/article?id={paper.doi}'
        try:
            html = await self.client.get_text(article_url)
            if not html:
                return
            figures = extract_plos_figures_from_html(html, doi=paper.doi)
            if figures:
                paper.figures = figures
            data_sources = extract_plos_data_from_html(html)
            if data_sources:
                paper.data_sources = data_sources
            self._merge_html_sections(paper, html)
        except Exception as exc:
            logger.warning('PLOS enrichment failed for %s: %s', paper.doi, exc)

    async def enrich_elife_paper(self, paper: PaperRecord) -> None:
        '''Enrich eLife paper with figures and data from the API.'''
        if not paper.doi:
            return
        # Extract article ID from DOI (e.g. "10.7554/eLife.12345" -> "12345")
        m = re.search(r'eLife\.(\d+)', paper.doi)
        if not m:
            return
        article_id = m.group(1)
        url = build_elife_article_url(article_id)
        try:
            json_data = await self.client.get_json(url)
            if not json_data:
                return
            # Parse figures from eLife article JSON
            figures = []
            for i, fig in enumerate(json_data.get('figures', []), start=1):
                from core.sources.journals.models import FigureInfo
                fig_id = fig.get('id', f'fig{i}')
                caption = fig.get('title', '')
                if fig.get('caption'):
                    caption = f"{caption} {fig['caption']}".strip()
                image_url = ''
                for source in fig.get('sources', []):
                    if source.get('mediaType', '').startswith('image/'):
                        image_url = source.get('uri', '')
                        break
                if not image_url:
                    image_section = fig.get('image', {})
                    if isinstance(image_section, dict):
                        image_url = image_section.get('uri', '')
                figures.append(FigureInfo(
                    figure_id=fig_id,
                    caption=caption,
                    full_size_url=image_url,
                ))
            if figures:
                paper.figures = figures
            # Parse data availability from eLife article JSON
            data_avail = json_data.get('dataSets', {})
            if data_avail:
                from core.sources.journals.models import DataSource
                from core.sources.journals.parsers.pmc_parser import DATA_REPO_PATTERNS
                da_text = str(data_avail)
                seen = set()
                data_sources = []
                for pattern, repo, url_template in DATA_REPO_PATTERNS:
                    for match in re.finditer(pattern, da_text):
                        accession = match.group(0)
                        key = (repo, accession)
                        if key not in seen:
                            seen.add(key)
                            data_sources.append(DataSource(
                                repository=repo,
                                accession=accession,
                                url=url_template.format(accession),
                            ))
                if data_sources:
                    paper.data_sources = data_sources
        except Exception as exc:
            logger.warning('eLife enrichment failed for %s: %s', paper.doi, exc)

    async def enrich_generic_paper(self, paper: PaperRecord) -> None:
        '''Generic enrichment: fetch article HTML and extract with BS4.'''
        if not paper.url:
            return
        try:
            html = await self.client.get_text(paper.url)
            if not html:
                return
            figures = extract_figures_bs4(html, base_url=paper.url)
            if figures:
                paper.figures = figures
            data_sources = extract_data_availability_bs4(html)
            if data_sources:
                paper.data_sources = data_sources
            self._merge_html_sections(paper, html)
        except Exception as exc:
            logger.warning('Generic enrichment failed for %s: %s', paper.doi, exc)

    @staticmethod
    def _merge_html_sections(paper: PaperRecord, html: str) -> None:
        '''Merge fulltext sections extracted from HTML into the paper record.'''
        html_secs = extract_fulltext_sections_bs4(html)
        if not html_secs:
            return
        if not paper.fulltext_sections:
            paper.fulltext_sections = {}
        for k, v in html_secs.items():
            if k not in paper.fulltext_sections or len(v) > len(paper.fulltext_sections.get(k, '')):
                paper.fulltext_sections[k] = v
