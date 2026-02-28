Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: LOAD_FAST_AND_CLEAR (241)
# Source Generated with Decompyle++
# File: nature_parser.pyc (Python 3.12)

'''
Nature family parser — Springer Nature API + HTML scraping fallback.

Strategy:
  1. Use Springer Nature Open Access API to discover articles
  2. For each article, fetch the HTML page from nature.com
  3. Extract high-res figures, captions, and data-availability links
'''
import re
from typing import List, Optional, Tuple
from langskills.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS

def build_springer_api_url(issn, journal_slug, start, page_size = None, api_key = None, year_from = None, year_to = ('', '', 1, 100, '', 2020, 2026, ''), subject = ('issn', str, 'journal_slug', str, 'start', int, 'page_size', int, 'api_key', str, 'year_from', int, 'year_to', int, 'subject', str, 'return', str)):
    '''Build a Springer Nature Open Access API query URL.'''
    base = 'https://api.springernature.com/openaccess/json'
    parts = []
    if issn:
        parts.append(f'''issn:{issn}''')
    if subject:
        parts.append(f'''subject:"{subject}"''')
    parts.append(f'''year:{year_from} TO {year_to}''')
    parts.append('type:Journal Article')
    query = ' AND '.join(parts)
    params = {
        'q': query,
        's': str(start),
        'p': str(page_size),
        'api_key': api_key }
    param_str = (lambda .0: pass# WARNING: Decompyle incomplete
)(params.items()())
    return f'''{base}?{param_str}'''


def parse_springer_api_response(json_data = None):
    '''Parse Springer API JSON response.

    Returns (list_of_article_metadata_dicts, total_results).
    '''
    records_raw = json_data.get('records', [])
    result_info = json_data.get('result', [
        { }])
    total = 0
    if result_info:
        total = int(result_info[0].get('total', 0))
    return (records_raw, total)


def springer_record_to_paper(record = None, journal_slug = None):
    '''Convert a single Springer API record dict to a PaperRecord (metadata only).'''
    doi = record.get('doi', '').strip()
    if not doi:
        return None
    title = record.get('title', '').strip()
    abstract = record.get('abstract', '').strip()
    pub_date = record.get('publicationDate', '').strip()
    journal_name = record.get('publicationName', '').strip()
    creators = record.get('creators', [])
# WARNING: Decompyle incomplete


def parse_nature_article_html(html = None, doi = None):
    '''Parse a nature.com article HTML page to extract figures and data links.

    Uses regex-based extraction to avoid heavy dependency on lxml/bs4 at import time.
    The actual crawler uses BeautifulSoup for robustness.
    '''
    figures = extract_figures_from_html(html)
    data_sources = extract_data_from_html(html)
    return (figures, data_sources)


def extract_figures_from_html(html = None):
    '''Extract figures from Nature article HTML.

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
    '''
    figures = []
    fig_idx = 0
    fig_pattern = re.compile('<figure[^>]*id=["\\\']([^"\\\']*)["\\\'][^>]*>(.*?)</figure>', re.DOTALL | re.IGNORECASE)
    for m in fig_pattern.finditer(html):
        fig_idx += 1
        fig_id = m.group(1)
        fig_block = m.group(2)
        cap_match = re.search('<figcaption[^>]*>(.*?)</figcaption>', fig_block, re.DOTALL | re.IGNORECASE)
        caption = _strip_tags(cap_match.group(1)) if cap_match else ''
        img_match = re.search('<img[^>]*(?:data-src|src)=["\\\']([^"\\\']+)["\\\']', fig_block, re.IGNORECASE)
        img_url = img_match.group(1) if img_match else ''
        full_url = _upgrade_to_fullsize(img_url)
        if not full_url:
            a_match = re.search('href=["\\\']([^"\\\']*figure[^"\\\']*)["\\\']', fig_block, re.IGNORECASE)
            if a_match:
                full_url = a_match.group(1)
                if not full_url.startswith('http'):
                    full_url = f'''https://www.nature.com{full_url}'''
        fig_type = 'main'
        if 'extended' in fig_id.lower() or 'extended' in caption.lower():
            fig_type = 'extended'
        elif 'supp' in fig_id.lower() or 'supplement' in caption.lower():
            fig_type = 'supplementary'
        if not full_url:
            full_url
        figures.append(FigureInfo(figure_id = fig_id, caption = caption, full_size_url = img_url, thumbnail_url = img_url if full_url else '', figure_type = fig_type))
    if not figures:
        pic_pattern = re.compile('<picture[^>]*>(.*?)</picture>', re.DOTALL | re.IGNORECASE)
        for m in pic_pattern.finditer(html):
            fig_idx += 1
            block = m.group(1)
            src_match = re.search('src=["\\\']([^"\\\']+)["\\\']', block)
            if not src_match:
                continue
            url = src_match.group(1)
            if not _upgrade_to_fullsize(url):
                _upgrade_to_fullsize(url)
            figures.append(FigureInfo(figure_id = f'''fig{fig_idx}''', caption = '', full_size_url = url))
    return figures


def extract_data_from_html(html = None):
    '''Extract data-availability section and accession links from Nature HTML.'''
    data_sources = []
    seen = set()
    da_pattern = re.compile('(?:data\\s+availab|data\\s+and\\s+code\\s+availab|code\\s+availab|accession)[^<]*((?:(?!</section|</div\\s*>\\s*<(?:section|div)[^>]*class=["\\\'](?:c-article-section|u-)).){100,5000})', re.DOTALL | re.IGNORECASE)
    text_blocks = []
    for m in da_pattern.finditer(html):
        text_blocks.append(_strip_tags(m.group(0)))
    link_pattern = re.compile('href=["\\\']([^"\\\']+)["\\\']', re.IGNORECASE)
    for m in da_pattern.finditer(html):
        for lm in link_pattern.finditer(m.group(0)):
            text_blocks.append(lm.group(1))
    full_text = ' '.join(text_blocks)
    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, full_text):
            accession = match.group(0)
            key = (repo, accession)
            if not key not in seen:
                continue
            seen.add(key)
            url = url_template.format(accession)
            data_sources.append(DataSource(repository = repo, accession = accession, url = url))
    return data_sources


def _upgrade_to_fullsize(url = None):
    '''Try to convert a Springer Nature thumbnail URL to full-size.'''
    if not url:
        return ''
    upgraded = re.sub('/(?:lw|m|w)\\d+/', '/full/', url)
    if upgraded != url:
        return upgraded


def _strip_tags(html_str = None):
    '''Remove HTML tags and normalize whitespace.'''
    text = re.sub('<[^>]+>', ' ', html_str)
    text = re.sub('\\s+', ' ', text).strip()
    return text

