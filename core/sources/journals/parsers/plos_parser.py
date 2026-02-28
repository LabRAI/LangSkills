"""
PLOS parser -- PLOS Search API + article HTML extraction.

All PLOS journals are fully open access (CC-BY).
The PLOS Search API is based on Solr and returns structured JSON.
"""
import re
from urllib.parse import urljoin, quote
from typing import List, Tuple, Optional

from core.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS

PLOS_JOURNAL_KEYS = {
    'plosone': 'PLoS ONE',
    'plosbiology': 'PLoS Biology',
    'plosmedicine': 'PLoS Medicine',
    'ploscompbiol': 'PLoS Computational Biology',
    'plosgenetics': 'PLoS Genetics',
    'plospathogens': 'PLoS Pathogens',
    'plosntds': 'PLoS Neglected Tropical Diseases',
}


def _encode_params(params: dict) -> str:
    """Encode a dict of parameters into a URL query string."""
    return '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in params.items())


def build_plos_search_url(
    journal_slug: str = '',
    start: int = 0,
    rows: int = 100,
    year_from: int = 2020,
    year_to: int = 2026,
) -> str:
    """Build a PLOS Search API URL."""
    base = 'https://api.plos.org/search'
    fq_parts = []
    if journal_slug and journal_slug in PLOS_JOURNAL_KEYS:
        jname = PLOS_JOURNAL_KEYS[journal_slug]
        fq_parts.append(f'journal:"{jname}"')
    fq_parts.append(
        f'publication_date:[{year_from}-01-01T00:00:00Z TO {year_to}-12-31T23:59:59Z]'
    )
    fq_parts.append('doc_type:full')
    fq = ' AND '.join(fq_parts)
    fl = 'id,title_display,abstract,author_display,journal,publication_date,figure_table_caption'
    params = {
        'q': '*:*',
        'fq': fq,
        'fl': fl,
        'start': str(start),
        'rows': str(rows),
        'sort': 'publication_date desc',
        'wt': 'json',
    }
    param_str = _encode_params(params)
    return f'{base}?{param_str}'


def parse_plos_search_response(json_data: dict = None) -> Tuple[list, int]:
    """Parse PLOS search JSON. Returns (docs, total_found)."""
    if json_data is None:
        json_data = {}
    resp = json_data.get('response', {})
    docs = resp.get('docs', [])
    total = resp.get('numFound', 0)
    return (docs, total)


def plos_doc_to_paper(doc: dict = None) -> Optional[PaperRecord]:
    """Convert a PLOS search result doc to PaperRecord (metadata + captions)."""
    if doc is None:
        doc = {}
    doi = doc.get('id', '').strip()
    if not doi:
        return None
    title = doc.get('title_display', '').strip()
    abstract_raw = doc.get('abstract')
    if isinstance(abstract_raw, list):
        abstract = abstract_raw[0] if abstract_raw else ''
    else:
        abstract = abstract_raw or ''
    authors = doc.get('author_display', [])
    journal = doc.get('journal', '').strip()
    pub_date = doc.get('publication_date', '')[:10]
    url = f'https://doi.org/{doi}'

    captions_raw = doc.get('figure_table_caption', [])
    figures = []
    for i, cap in enumerate(captions_raw):
        if not cap:
            continue
        fig_id = f'fig{i + 1}'
        fig_num = f'g{str(i + 1).zfill(3)}'
        plos_slug = _doi_to_plos_slug(doi)
        full_url = (
            f'https://journals.plos.org/{plos_slug}/article/figure/image?id={doi}.{fig_num}&size=large'
        )
        figures.append(FigureInfo(
            figure_id=fig_id,
            caption=cap.strip(),
            full_size_url=full_url,
            figure_type='main',
        ))

    return PaperRecord(
        doi=doi,
        title=title,
        journal=journal,
        journal_family='PLOS',
        authors=authors,
        abstract=abstract if isinstance(abstract, str) else str(abstract),
        pub_date=pub_date,
        url=url,
        figures=figures,
        is_open_access=True,
    )


def extract_plos_figures_from_html(
    html: str = '',
    doi: str = '',
) -> List[FigureInfo]:
    """Extract figures from a PLOS article HTML page for more reliable extraction."""
    if not html:
        return []
    text = str(html).strip()
    if not text:
        return []

    from bs4 import BeautifulSoup

    doi = str(doi or '').strip()
    slug = _doi_to_plos_slug(doi) if doi else 'plosone'
    if not slug:
        slug = 'plosone'
    base_page_url = (
        f'https://journals.plos.org/{slug}/article?id={doi}'
        if doi
        else f'https://journals.plos.org/{slug}/'
    )

    def _normalize_ws(s: str = '') -> str:
        if not s:
            return ''
        return re.sub(r'\s+', ' ', str(s)).strip()

    def _asset_to_id_and_type(asset: str = '') -> Tuple[str, str]:
        if not asset:
            return ('', '')
        a = str(asset).strip()
        m = re.search(r'\.([A-Za-z])(\d+)\s*$', a)
        if not m:
            return ('', '')
        prefix = str(m.group(1)).strip().lower()
        num = int(m.group(2))
        if prefix == 'g':
            if num > 0:
                return (f'fig{num}', 'main')
            return ('', 'main')
        elif prefix == 't':
            if num > 0:
                return (f'table{num}', 'table')
            return ('', 'table')
        elif prefix == 's':
            if num > 0:
                return (f'supp{num}', 'supplementary')
            return ('', 'supplementary')
        elif prefix and num > 0:
            return (f'{prefix}{num}', 'main')
        return ('', 'main')

    def _best_image_href(tag) -> str:
        candidates = []
        for a in tag.find_all('a', href=True):
            href = str(a.get('href', '')).strip()
            if not href:
                continue
            h = href.lower()
            if 'article/figure/image' not in h:
                continue
            score = 0
            if 'size=large' in h:
                score += 100
            elif 'size=medium' in h:
                score += 60
            elif 'size=inline' in h:
                score += 20
            if 'download' in h:
                score += 10
            if 'size=original' in h:
                score -= 20
            candidates.append((score, href))
        if not candidates:
            return ''
        candidates.sort(key=lambda x: x[0], reverse=True)
        return str(candidates[0][1])

    soup = BeautifulSoup(text, 'html.parser')
    out: List[FigureInfo] = []
    seen_assets: set = set()

    for fig_div in soup.find_all('div', class_='figure'):
        asset = str(fig_div.get('data-doi', '')).strip()
        if not asset or asset in seen_assets:
            continue
        seen_assets.add(asset)

        (figure_id, fig_type) = _asset_to_id_and_type(asset)
        if not figure_id:
            figure_id = f'fig{len(out) + 1}'
        if not fig_type:
            fig_type = 'main'

        cap_parts = []
        cap_div = fig_div.find(
            'div', class_=re.compile(r'\bfigcaption\b', flags=re.IGNORECASE)
        )
        if cap_div:
            cap_parts.append(_normalize_ws(cap_div.get_text(' ', strip=True)))

        for p in fig_div.find_all('p'):
            classes = p.get('class', [])
            if isinstance(classes, str):
                classes = [classes]
            cls = ' '.join(str(c).lower() for c in classes)
            if 'caption_object' in cls:
                continue
            txt = _normalize_ws(p.get_text(' ', strip=True))
            if txt and (txt.startswith('http://') or txt.startswith('https://')):
                continue
            if txt:
                cap_parts.append(txt)

        # Deduplicate caption parts
        caption = ''
        seen_txt: set = set()
        deduped = []
        for part in cap_parts:
            t = _normalize_ws(part)
            if not t or t in seen_txt:
                continue
            seen_txt.add(t)
            deduped.append(t)
        if deduped:
            caption = ' '.join(deduped).strip()

        img = fig_div.find('img')
        thumb_href = str(img.get('src', '')).strip() if img else ''
        full_href = _best_image_href(fig_div) or thumb_href
        full_url = urljoin(base_page_url, full_href) if full_href else ''
        thumb_url = urljoin(base_page_url, thumb_href) if thumb_href else ''

        out.append(FigureInfo(
            figure_id=figure_id,
            caption=caption,
            full_size_url=full_url,
            thumbnail_url=thumb_url if thumb_url and thumb_url != full_url else '',
            figure_type=fig_type,
        ))

    return out


def extract_plos_data_from_html(html: str = '') -> List[DataSource]:
    """Extract data availability info from PLOS HTML."""
    if not html:
        return []

    data_sources = []
    seen = set()
    da_match = re.search(
        r'(?:data\s+availability|supporting\s+information)(.*?)(?:<h\d|</article|$)',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    text = _strip_tags(da_match.group(1)) if da_match else ''
    if da_match:
        for lm in re.finditer(r'href=["\']([^"\']+)["\']', da_match.group(1)):
            text += f' {lm.group(1)}'

    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, text):
            accession = match.group(0)
            key = (repo, accession)
            if key not in seen:
                seen.add(key)
                url = url_template.format(accession)
                data_sources.append(DataSource(
                    repository=repo, accession=accession, url=url
                ))

    return data_sources


def _doi_to_plos_slug(doi: str = '') -> str:
    """Convert a PLOS DOI to a journal slug for URL construction."""
    mapping = {
        'journal.pone': 'plosone',
        'journal.pbio': 'plosbiology',
        'journal.pmed': 'plosmedicine',
        'journal.pcbi': 'ploscompbiol',
        'journal.pgen': 'plosgenetics',
        'journal.ppat': 'plospathogens',
        'journal.pntd': 'plosntds',
    }
    for key, slug in mapping.items():
        if key in doi:
            return slug
    return 'plosone'


def _strip_tags(html_str: str = '') -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html_str)
    text = re.sub(r'\s+', ' ', text).strip()
    return text
