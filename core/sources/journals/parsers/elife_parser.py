"""
eLife parser -- eLife REST API.

eLife is fully OA and has an excellent API.
API docs: https://api.elifesciences.org
"""
import re
from typing import List, Tuple, Optional
from urllib.parse import quote

from core.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS


def _encode_params(params: dict) -> str:
    """Encode a dict of parameters into a URL query string."""
    return '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in params.items())


def build_elife_search_url(
    page: int = 1,
    per_page: int = 100,
    year_from: int = 2020,
    subject: str = '',
    order: str = 'desc',
) -> str:
    """Build eLife API search URL."""
    base = 'https://api.elifesciences.org/search'
    params = {
        'for': '',
        'page': str(page),
        'per-page': str(per_page),
        'sort': 'date',
        'order': order,
        'type[]': 'research-article',
        'start-date': f'{year_from}-01-01',
        'end-date': '2026-12-31',
    }
    if subject:
        params['subject[]'] = subject
    param_str = _encode_params(params)
    return f'{base}?{param_str}'


def build_elife_article_url(article_id: str = '') -> str:
    """Build URL to fetch full article JSON from eLife API."""
    return f'https://api.elifesciences.org/articles/{article_id}'


def parse_elife_search_response(json_data: dict = None) -> Tuple[list, int]:
    """Parse eLife search response. Returns (items, total)."""
    if json_data is None:
        json_data = {}
    items = json_data.get('items', [])
    total = json_data.get('total', 0)
    return (items, total)


def elife_item_to_paper_stub(item: dict = None) -> Optional[PaperRecord]:
    """Convert an eLife search result item to a PaperRecord stub (no figures yet)."""
    if item is None:
        item = {}
    article_id = item.get('id', '')
    if not article_id:
        return None
    doi = item.get('doi', f'10.7554/eLife.{article_id}')
    title = item.get('title', '')
    pub_date = item.get('published', '')[:10]
    authors = []
    for a in item.get('authors', []):
        name = a.get('name', {})
        if isinstance(name, dict):
            preferred = name.get('preferred', '')
            if not preferred:
                continue
            authors.append(preferred)
            continue
        if isinstance(name, str):
            authors.append(name)
    return PaperRecord(
        doi=doi,
        title=title,
        journal='eLife',
        journal_family='eLife',
        authors=authors,
        pub_date=pub_date,
        url=f'https://elifesciences.org/articles/{article_id}',
        is_open_access=True,
    )


def parse_elife_article_json(json_data: dict = None, article_id: str = '') -> Tuple[List[FigureInfo], List[DataSource]]:
    """Parse a full eLife article JSON response to extract figures and data sources.

    Returns (figures, data_sources).
    """
    if json_data is None:
        json_data = {}

    figures: List[FigureInfo] = []
    data_sources: List[DataSource] = []

    # Extract figures from the 'content' or 'body' field
    body = json_data.get('body', [])
    _extract_figures_from_body(body, figures)

    # Extract from 'figures' or 'additionalFiles' if present
    for fig_item in json_data.get('figures', []):
        fig_id = fig_item.get('id', f'fig{len(figures) + 1}')
        title = fig_item.get('title', '')
        caption_parts = []
        if title:
            caption_parts.append(title)
        caption_content = fig_item.get('caption', [])
        if isinstance(caption_content, list):
            for block in caption_content:
                if isinstance(block, dict):
                    caption_parts.append(block.get('text', ''))
                elif isinstance(block, str):
                    caption_parts.append(block)
        elif isinstance(caption_content, str):
            caption_parts.append(caption_content)
        caption = ' '.join(caption_parts).strip()

        img_url = ''
        image = fig_item.get('image', {})
        if isinstance(image, dict):
            img_url = image.get('uri', '') or image.get('source', {}).get('uri', '')

        fig_type = 'main'
        if 'supplement' in fig_id.lower() or 'supp' in fig_id.lower():
            fig_type = 'supplementary'

        figures.append(FigureInfo(
            figure_id=fig_id,
            caption=caption,
            full_size_url=img_url,
            figure_type=fig_type,
        ))

    # Extract data availability
    data_avail = json_data.get('dataSets', {})
    if isinstance(data_avail, dict):
        for section_key in ('generated', 'used'):
            for ds in data_avail.get(section_key, []):
                uri = ds.get('uri', '')
                accession = ds.get('id', '') or ds.get('accession', '')
                repo = ds.get('database', '') or ds.get('repository', '')
                if uri or accession:
                    data_sources.append(DataSource(
                        repository=repo,
                        accession=accession,
                        url=uri,
                    ))

    # Also scan text for known accession patterns
    all_text = _collect_text(json_data)
    seen = {(ds.repository, ds.accession) for ds in data_sources}
    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, all_text):
            accession = match.group(0)
            key = (repo, accession)
            if key not in seen:
                seen.add(key)
                url = url_template.format(accession)
                data_sources.append(DataSource(repository=repo, accession=accession, url=url))

    return (figures, data_sources)


def _extract_figures_from_body(body_blocks: list, figures: List[FigureInfo]) -> None:
    """Recursively extract figure references from eLife article body blocks."""
    if not isinstance(body_blocks, list):
        return
    for block in body_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get('type', '')
        if block_type == 'figure':
            fig_id = block.get('id', f'fig{len(figures) + 1}')
            caption = block.get('title', '')
            img_url = ''
            image = block.get('image', {})
            if isinstance(image, dict):
                img_url = image.get('uri', '')
            figures.append(FigureInfo(
                figure_id=fig_id,
                caption=caption,
                full_size_url=img_url,
                figure_type='main',
            ))
        # Recurse into nested content
        content = block.get('content', [])
        if isinstance(content, list):
            _extract_figures_from_body(content, figures)


def _collect_text(obj, parts: Optional[List[str]] = None) -> str:
    """Recursively collect all string values from a nested JSON structure."""
    if parts is None:
        parts = []
    if isinstance(obj, str):
        parts.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_text(v, parts)
    elif isinstance(obj, list):
        for item in obj:
            _collect_text(item, parts)
    return ' '.join(parts)
