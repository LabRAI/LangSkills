Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: PUSH_EXC_INFO (105)
Unsupported opcode: PUSH_EXC_INFO (105)
# Source Generated with Decompyle++
# File: plos_parser.pyc (Python 3.12)

'''
PLOS parser — PLOS Search API + article HTML extraction.

All PLOS journals are fully open access (CC-BY).
The PLOS Search API is based on Solr and returns structured JSON.
'''
import re
from urllib.parse import urljoin
from typing import List, Tuple, Optional
from langskills.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS
PLOS_JOURNAL_KEYS = {
    'plosone': 'PLoS ONE',
    'plosbiology': 'PLoS Biology',
    'plosmedicine': 'PLoS Medicine',
    'ploscompbiol': 'PLoS Computational Biology',
    'plosgenetics': 'PLoS Genetics',
    'plospathogens': 'PLoS Pathogens',
    'plosntds': 'PLoS Neglected Tropical Diseases' }

def build_plos_search_url(journal_slug = None, start = None, rows = None, year_from = ('', 0, 100, 2020, 2026), year_to = ('journal_slug', str, 'start', int, 'rows', int, 'year_from', int, 'year_to', int, 'return', str)):
    '''Build a PLOS Search API URL.'''
    base = 'https://api.plos.org/search'
    fq_parts = []
    if journal_slug and journal_slug in PLOS_JOURNAL_KEYS:
        jname = PLOS_JOURNAL_KEYS[journal_slug]
        fq_parts.append(f'''journal:"{jname}"''')
    fq_parts.append(f'''publication_date:[{year_from}-01-01T00:00:00Z TO {year_to}-12-31T23:59:59Z]''')
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
        'wt': 'json' }
    param_str = (lambda .0: pass# WARNING: Decompyle incomplete
)(params.items()())
    return f'''{base}?{param_str}'''


def parse_plos_search_response(json_data = None):
    '''Parse PLOS search JSON. Returns (docs, total_found).'''
    resp = json_data.get('response', { })
    docs = resp.get('docs', [])
    total = resp.get('numFound', 0)
    return (docs, total)


def plos_doc_to_paper(doc = None):
    '''Convert a PLOS search result doc to PaperRecord (metadata + captions).'''
    doi = doc.get('id', '').strip()
    if not doi:
        return None
    title = doc.get('title_display', '').strip()
    abstract = doc.get('abstract', [
        ''])[0] if isinstance(doc.get('abstract'), list) else doc.get('abstract', '')
    authors = doc.get('author_display', [])
    journal = doc.get('journal', '').strip()
    pub_date = doc.get('publication_date', '')[:10]
    url = f'''https://doi.org/{doi}'''
    captions_raw = doc.get('figure_table_caption', [])
    figures = []
    for i, cap in enumerate(captions_raw):
        if not cap:
            continue
        fig_id = f'''fig{i + 1}'''
        fig_num = f'''g{str(i + 1).zfill(3)}'''
        plos_slug = _doi_to_plos_slug(doi)
        figures.append(FigureInfo(figure_id = fig_id, caption = cap.strip(), full_size_url = full_url, figure_type = 'main'))
    return PaperRecord(doi = doi, title = title, journal = journal, journal_family = 'PLOS', authors = authors, abstract = abstract if isinstance(abstract, str) else str(abstract), pub_date = pub_date, url = url, figures = figures, is_open_access = True)


def extract_plos_figures_from_html(html = None, doi = None):
    '''Extract figures from a PLOS article HTML page for more reliable extraction.'''
    if not html:
        html
    text = str('').strip()
    if not text:
        return []
    BeautifulSoup = BeautifulSoup
    import bs4
    if not doi:
        doi
    doi = str('').strip()
    slug = _doi_to_plos_slug(doi) if doi else 'plosone'
    if not slug:
        slug
    if not str('plosone').strip():
        str('plosone').strip()
    slug = 'plosone'
    base_page_url = f'''https://journals.plos.org/{slug}/article?id={doi}''' if doi else f'''https://journals.plos.org/{slug}/'''
    
    def _normalize_ws(s = None):
        if not s:
            s
        return re.sub('\\s+', ' ', str('')).strip()

    
    def _asset_to_id_and_type(asset = None):
        if not asset:Unsupported opcode: RETURN_GENERATOR (109)

            asset
        a = str('').strip()
        m = re.search('\\.([A-Za-z])(\\d+)\\s*$', a)
        if not m:
            return ('', '')
        if not m.group(1):
            m.group(1)
        prefix = str('').strip().lower()
        num = int(m.group(2))
        if prefix == 'g':
            if num > 0:
                return (f'''fig{num}''', 'main')
            return (None, 'main')
        if None == 't':
            if num > 0:
                return (f'''table{num}''', 'table')
            return (None, 'table')
        if None == 's':
            if num > 0:
                return (f'''supp{num}''', 'supplementary')
            return (None, 'supplementary')
        if None and num > 0:
            return (f'''{prefix}{num}''', 'main')
        return (None, 'main')
    # WARNING: Decompyle incomplete

    
    def _best_image_href(tag = None):
        candidates = []
        for a in tag.find_all('a', href = True):
            if not a.get('href'):
                a.get('href')
            href = str('').strip()
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
        candidates.sort(key = (lambda x: int(x[0])), reverse = True)
        return str(candidates[0][1])

    soup = BeautifulSoup(text, 'html.parser')
    out = []
    seen_assets = set()
    for fig_div in soup.find_all('div', class_ = 'figure'):
        if not fig_div.get('data-doi'):
            fig_div.get('data-doi')
        asset = str('').strip()
        if asset or asset in seen_assets:
            continue
        seen_assets.add(asset)
        (figure_id, fig_type) = _asset_to_id_and_type(asset)
        if not figure_id:
            figure_id = f'''fig{len(out) + 1}'''
        if not fig_type:
            fig_type
        fig_type = 'main'
        cap_parts = []
        cap_div = fig_div.find('div', class_ = re.compile('\\bfigcaption\\b', flags = re.IGNORECASE))
        if cap_div:
            cap_parts.append(_normalize_ws(cap_div.get_text(' ', strip = True)))
        for p in fig_div.find_all('p'):
            if not p.get('class'):
                p.get('class')
            classes = []
            if isinstance(classes, str):
                classes = [
                    classes]
            cls = (lambda .0: pass# WARNING: Decompyle incomplete
)(classes())
            if 'caption_object' in cls:
                continue
            txt = _normalize_ws(p.get_text(' ', strip = True))
            if txt and txt.startswith('http://') or txt.startswith('https://'):
                continue
            cap_parts.append(txt)
        caption = ''
        seen_txt = set()
        deduped = []
        for part in cap_parts:
            t = _normalize_ws(part)
            if t or t in seen_txt:
                continue
            seen_txt.add(t)
            deduped.append(t)
        if deduped:
            caption = ' '.join(deduped).strip()
        img = fig_div.find('img')
        thumb_href = str('').strip() if img else ''
        if not _best_image_href(fig_div):
            _best_image_href(fig_div)
        full_href = thumb_href
        full_url = urljoin(base_page_url, full_href) if full_href else ''
        thumb_url = urljoin(base_page_url, thumb_href) if thumb_href else ''
        out.append(FigureInfo(figure_id = figure_id, caption = caption, full_size_url = full_url, thumbnail_url = thumb_url if thumb_url and thumb_url != full_url else '', figure_type = fig_type))
    return out
# WARNING: Decompyle incomplete


def extract_plos_data_from_html(html = None):
    '''Extract data availability info from PLOS HTML.'''
    data_sources = []
    seen = set()
    da_match = re.search('(?:data\\s+availability|supporting\\s+information)(.*?)(?:<h\\d|</article|$)', html, re.DOTALL | re.IGNORECASE)
    text = _strip_tags(da_match.group(1)) if da_match else ''
    if da_match:
        for lm in re.finditer('href=["\\\']([^"\\\']+)["\\\']', da_match.group(1)):
            text += f''' {lm.group(1)}'''
    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, text):
            accession = match.group(0)
            key = (repo, accession)
            if not key not in seen:
                continue
            seen.add(key)
            url = url_template.format(accession)
            data_sources.append(DataSource(repository = repo, accession = accession, url = url))
    return data_sources


def _doi_to_plos_slug(doi = None):
    '''Convert a PLOS DOI to a journal slug for URL construction.'''
    mapping = {
        'journal.pone': 'plosone',
        'journal.pbio': 'plosbiology',
        'journal.pmed': 'plosmedicine',
        'journal.pcbi': 'ploscompbiol',
        'journal.pgen': 'plosgenetics',
        'journal.ppat': 'plospathogens',
        'journal.pntd': 'plosntds' }
    for key, slug in mapping.items():
        if not key in doi:
            continue
        
        return mapping.items(), slug
    return 'plosone'


def _strip_tags(html_str = None):
    text = re.sub('<[^>]+>', ' ', html_str)
    text = re.sub('\\s+', ' ', text).strip()
    return text

