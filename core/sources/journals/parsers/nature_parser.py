"""
Nature family parser -- Springer Nature API + HTML scraping fallback.

Strategy:
  1. Use Springer Nature Open Access API to discover articles
  2. For each article, fetch the HTML page from nature.com
  3. Extract high-res figures, captions, and data-availability links
"""
import re
from typing import List, Optional, Tuple
from urllib.parse import quote

from core.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS


def _encode_params(params: dict) -> str:
    """Encode a dict of parameters into a URL query string."""
    return '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in params.items())


def build_springer_api_url(
    issn: str = '',
    journal_slug: str = '',
    start: int = 1,
    page_size: int = 100,
    api_key: str = '',
    year_from: int = 2020,
    year_to: int = 2026,
    subject: str = '',
) -> str:
    """Build a Springer Nature Open Access API query URL."""
    base = 'https://api.springernature.com/openaccess/json'
    parts = []
    if issn:
        parts.append(f'issn:{issn}')
    if subject:
        parts.append(f'subject:"{subject}"')
    parts.append(f'year:{year_from} TO {year_to}')
    parts.append('type:Journal Article')
    query = ' AND '.join(parts)
    params = {
        'q': query,
        's': str(start),
        'p': str(page_size),
        'api_key': api_key,
    }
    param_str = _encode_params(params)
    return f'{base}?{param_str}'


def parse_springer_api_response(json_data: dict = None) -> Tuple[list, int]:
    """Parse Springer API JSON response.

    Returns (list_of_article_metadata_dicts, total_results).
    """
    if json_data is None:
        json_data = {}
    records_raw = json_data.get('records', [])
    result_info = json_data.get('result', [{}])
    total = 0
    if result_info:
        total = int(result_info[0].get('total', 0))
    return (records_raw, total)


def springer_record_to_paper(
    record: dict = None,
    journal_slug: str = '',
) -> Optional[PaperRecord]:
    """Convert a single Springer API record dict to a PaperRecord (metadata only)."""
    if record is None:
        record = {}
    doi = record.get('doi', '').strip()
    if not doi:
        return None
    title = record.get('title', '').strip()
    abstract = record.get('abstract', '').strip()
    pub_date = record.get('publicationDate', '').strip()
    journal_name = record.get('publicationName', '').strip()
    creators = record.get('creators', [])
    authors = []
    for c in creators:
        name = c.get('creator', '').strip()
        if name:
            authors.append(name)

    url = f'https://doi.org/{doi}'
    if journal_slug:
        # Nature articles typically have a slug-based URL
        url = f'https://www.nature.com/{journal_slug}/articles/{doi.split("/")[-1]}'

    return PaperRecord(
        doi=doi,
        title=title,
        journal=journal_name,
        journal_family='Nature',
        authors=authors,
        abstract=abstract,
        pub_date=pub_date,
        url=url,
        is_open_access=True,
    )


def parse_nature_article_html(
    html: str = '',
    doi: str = '',
) -> Tuple[List[FigureInfo], List[DataSource]]:
    """Parse a nature.com article HTML page to extract figures and data links.

    Uses regex-based extraction to avoid heavy dependency on lxml/bs4 at import time.
    The actual crawler uses BeautifulSoup for robustness.
    """
    figures = extract_figures_from_html(html)
    data_sources = extract_data_from_html(html)
    return (figures, data_sources)


def extract_figures_from_html(html: str = '') -> List[FigureInfo]:
    """Extract figures from Nature article HTML.

    Nature uses patterns like:
      <figure id="Fig1"> or <figure id="fig1">
        <a data-test="figure-link" href="/articles/..."> ... </a>
        <img src="..." data-src="..." alt="..." />
        <figcaption> ... </figcaption>
      </figure>

    Full-size images are typically at:
      https://media.springernature.com/full/springer-static/image/art%3A{doi_encoded}/MediaObjects/{filename}
    or:
      https://www.nature.com/articles/{slug}/figures/{fig_num}
    """
    if not html:
        return []

    figures = []
    fig_idx = 0
    fig_pattern = re.compile(
        r'<figure[^>]*id=["\']([^"\']*)["\'][^>]*>(.*?)</figure>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in fig_pattern.finditer(html):
        fig_idx += 1
        fig_id = m.group(1)
        fig_block = m.group(2)

        cap_match = re.search(
            r'<figcaption[^>]*>(.*?)</figcaption>', fig_block, re.DOTALL | re.IGNORECASE
        )
        caption = _strip_tags(cap_match.group(1)) if cap_match else ''

        img_match = re.search(
            r'<img[^>]*(?:data-src|src)=["\']([^"\']+)["\']', fig_block, re.IGNORECASE
        )
        img_url = img_match.group(1) if img_match else ''
        full_url = _upgrade_to_fullsize(img_url)

        if not full_url:
            a_match = re.search(
                r'href=["\']([^"\']*figure[^"\']*)["\']', fig_block, re.IGNORECASE
            )
            if a_match:
                full_url = a_match.group(1)
                if not full_url.startswith('http'):
                    full_url = f'https://www.nature.com{full_url}'

        fig_type = 'main'
        if 'extended' in fig_id.lower() or 'extended' in caption.lower():
            fig_type = 'extended'
        elif 'supp' in fig_id.lower() or 'supplement' in caption.lower():
            fig_type = 'supplementary'

        figures.append(FigureInfo(
            figure_id=fig_id,
            caption=caption,
            full_size_url=full_url if full_url else img_url,
            thumbnail_url=img_url if full_url else '',
            figure_type=fig_type,
        ))

    # Fallback: try <picture> elements if no <figure> found
    if not figures:
        pic_pattern = re.compile(
            r'<picture[^>]*>(.*?)</picture>', re.DOTALL | re.IGNORECASE
        )
        for m in pic_pattern.finditer(html):
            fig_idx += 1
            block = m.group(1)
            src_match = re.search(r'src=["\']([^"\']+)["\']', block)
            if not src_match:
                continue
            url = src_match.group(1)
            full = _upgrade_to_fullsize(url)
            figures.append(FigureInfo(
                figure_id=f'fig{fig_idx}',
                caption='',
                full_size_url=full if full else url,
            ))

    return figures


def extract_data_from_html(html: str = '') -> List[DataSource]:
    """Extract data-availability section and accession links from Nature HTML."""
    if not html:
        return []

    data_sources = []
    seen = set()

    da_pattern = re.compile(
        r'(?:data\s+availab|data\s+and\s+code\s+availab|code\s+availab|accession)'
        r'[^<]*((?:(?!</section|</div\s*>\s*<(?:section|div)[^>]*class=["\']'
        r'(?:c-article-section|u-)).){100,5000})',
        re.DOTALL | re.IGNORECASE,
    )

    text_blocks = []
    for m in da_pattern.finditer(html):
        text_blocks.append(_strip_tags(m.group(0)))

    link_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
    for m in da_pattern.finditer(html):
        for lm in link_pattern.finditer(m.group(0)):
            text_blocks.append(lm.group(1))

    full_text = ' '.join(text_blocks)
    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, full_text):
            accession = match.group(0)
            key = (repo, accession)
            if key not in seen:
                seen.add(key)
                url = url_template.format(accession)
                data_sources.append(DataSource(
                    repository=repo, accession=accession, url=url
                ))

    return data_sources


def _upgrade_to_fullsize(url: str = '') -> str:
    """Try to convert a Springer Nature thumbnail URL to full-size."""
    if not url:
        return ''
    upgraded = re.sub(r'/(?:lw|m|w)\d+/', '/full/', url)
    if upgraded != url:
        return upgraded
    return ''


def _strip_tags(html_str: str = '') -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html_str)
    text = re.sub(r'\s+', ' ', text).strip()
    return text
