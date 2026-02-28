"""
PMC (PubMed Central) parser -- the universal backbone.

Most OA articles from Nature, Science, Cell, PLOS, etc. are deposited in PMC.
We use the NCBI E-utilities API (esearch + efetch) to:
  1. Search for OA articles by journal ISSN
  2. Fetch full XML (PMC OA subset)
  3. Extract figures, captions, and data-availability statements
"""
import re
import xml.etree.ElementTree as etree
from typing import List, Optional, Tuple
from urllib.parse import quote

from core.sources.journals.models import DataSource, FigureInfo, PaperRecord

DATA_REPO_PATTERNS = [
    (r'GSE\d{4,8}', 'GEO', 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={}'),
    (r'GSM\d{4,8}', 'GEO', 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={}'),
    (r'(?:SRP|SRR|SRX|SRS|PRJNA)\d{4,10}', 'SRA', 'https://www.ncbi.nlm.nih.gov/sra/{}'),
    (r'PRJNA\d{4,10}', 'BioProject', 'https://www.ncbi.nlm.nih.gov/bioproject/{}'),
    (r'E-[A-Z]{4}-\d{1,8}', 'ArrayExpress', 'https://www.ebi.ac.uk/arrayexpress/experiments/{}'),
    (r'\b[0-9][A-Za-z0-9]{3}\b', 'PDB', 'https://www.rcsb.org/structure/{}'),
    (r'10\.5281/zenodo\.\d+', 'Zenodo', 'https://doi.org/{}'),
    (r'10\.6084/m9\.figshare\.\d+', 'Figshare', 'https://doi.org/{}'),
    (r'10\.5061/dryad\.[a-z0-9]+', 'Dryad', 'https://doi.org/{}'),
    (r'github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'GitHub', 'https://{}'),
    (r'EMD-\d{4,6}', 'EMDB', 'https://www.ebi.ac.uk/emdb/{}'),
    (r'[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}', 'UniProt', 'https://www.uniprot.org/uniprot/{}'),
    (r'(?:ERR|ERX|ERS|ERA|ERP)\d{6,10}', 'ENA', 'https://www.ebi.ac.uk/ena/browser/view/{}'),
    (r'phs\d{6}', 'dbGaP', 'https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id={}'),
    (r'PXD\d{6}', 'PRIDE', 'https://www.ebi.ac.uk/pride/archive/projects/{}'),
    (r'MTBLS\d+', 'MetaboLights', 'https://www.ebi.ac.uk/metabolights/{}'),
]


def _encode_params(params: dict) -> str:
    """Encode a dict of parameters into a URL query string."""
    return '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in params.items())


def build_esearch_url(
    issn: str = '',
    journal_name: str = '',
    retmax: int = 500,
    retstart: int = 0,
    min_date: str = '2020/01/01',
    max_date: str = '2026/12/31',
    api_key: str = '',
) -> str:
    """Build an E-utilities esearch URL for PMC OA articles."""
    base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    parts = ['open access[filter]']
    if issn:
        parts.append(f'{issn}[journal]')
    elif journal_name:
        parts.append(f'"{journal_name}"[journal]')
    query = ' AND '.join(parts)
    params = {
        'db': 'pmc',
        'term': query,
        'retmax': str(retmax),
        'retstart': str(retstart),
        'retmode': 'json',
        'datetype': 'pdat',
        'mindate': min_date,
        'maxdate': max_date,
        'sort': 'pub_date',
        'usehistory': 'y',
    }
    if api_key:
        params['api_key'] = api_key
    param_str = _encode_params(params)
    return f'{base}?{param_str}'


def build_efetch_url(
    pmc_ids: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> str:
    """Build an E-utilities efetch URL to get full XML for a batch of PMC IDs."""
    base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    id_str = ','.join(pmc_ids or [])
    params = {
        'db': 'pmc',
        'id': id_str,
        'retmode': 'xml',
    }
    if api_key:
        params['api_key'] = api_key
    param_str = _encode_params(params)
    return f'{base}?{param_str}'


def parse_esearch_response(json_data: dict = None) -> Tuple[List[str], int]:
    """Parse esearch JSON response. Returns (list_of_pmc_ids, total_count)."""
    if json_data is None:
        json_data = {}
    result = json_data.get('esearchresult', {})
    id_list = result.get('idlist', [])
    total = int(result.get('count', 0))
    return (id_list, total)


def parse_article_xml(article_elem) -> Optional[PaperRecord]:
    """Parse a single <article> element from PMC efetch XML into a PaperRecord."""
    front = article_elem.find('.//front')
    if front is None:
        return None

    # -- Extract metadata from <front> --
    article_meta = front.find('.//article-meta')
    if article_meta is None:
        return None

    # DOI
    doi = ''
    for aid in article_meta.findall('.//article-id'):
        if aid.get('pub-id-type') == 'doi':
            doi = (aid.text or '').strip()
            break

    # PMC ID
    pmc_id = ''
    for aid in article_meta.findall('.//article-id'):
        if aid.get('pub-id-type') == 'pmc':
            pmc_id = (aid.text or '').strip()
            break

    # Title
    title_elem = article_meta.find('.//article-title')
    title = _elem_text(title_elem) if title_elem is not None else ''

    # Journal
    journal_meta = front.find('.//journal-meta')
    journal = ''
    if journal_meta is not None:
        jt = journal_meta.find('.//journal-title')
        if jt is not None:
            journal = (jt.text or '').strip()

    # Authors
    authors = []
    for contrib in article_meta.findall('.//contrib[@contrib-type="author"]'):
        name_elem = contrib.find('name')
        if name_elem is not None:
            surname = (name_elem.findtext('surname') or '').strip()
            given = (name_elem.findtext('given-names') or '').strip()
            if surname:
                authors.append(f'{given} {surname}'.strip())

    # Publication date
    pub_date = ''
    for pd in article_meta.findall('.//pub-date'):
        year = pd.findtext('year') or ''
        month = (pd.findtext('month') or '01').zfill(2)
        day = (pd.findtext('day') or '01').zfill(2)
        if year:
            pub_date = f'{year}-{month}-{day}'
            break

    # Abstract
    abstract_elem = article_meta.find('.//abstract')
    abstract = _elem_text(abstract_elem) if abstract_elem is not None else ''

    # -- Extract figures from <body> --
    figures = []
    body = article_elem.find('.//body')
    if body is not None:
        for fig in body.findall('.//fig'):
            fig_id = fig.get('id', '')
            label = (fig.findtext('label') or '').strip()
            caption_elem = fig.find('caption')
            caption = _elem_text(caption_elem) if caption_elem is not None else ''
            if label and caption and not caption.startswith(label):
                caption = f'{label}. {caption}'

            graphic = fig.find('.//graphic')
            img_url = ''
            if graphic is not None:
                href = graphic.get('{http://www.w3.org/1999/xlink}href', '')
                if href:
                    img_url = f'https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/bin/{href}.jpg'

            fig_type = 'main'
            if 'supp' in fig_id.lower():
                fig_type = 'supplementary'
            elif 'extended' in fig_id.lower():
                fig_type = 'extended'

            figures.append(FigureInfo(
                figure_id=fig_id or label or f'fig{len(figures) + 1}',
                caption=caption,
                full_size_url=img_url,
                figure_type=fig_type,
            ))

    # -- Extract data availability --
    data_sources = _extract_data_sources(article_elem)

    return PaperRecord(
        doi=doi,
        title=title,
        journal=journal,
        journal_family='PMC',
        authors=authors,
        abstract=abstract,
        pub_date=pub_date,
        url=f'https://doi.org/{doi}' if doi else '',
        figures=figures,
        data_sources=data_sources,
        is_open_access=True,
        pmc_id=pmc_id,
    )


def _extract_data_sources(article_elem) -> List[DataSource]:
    """Extract data repository references from the article XML."""
    data_sources: List[DataSource] = []
    seen: set = set()

    # Gather text from data-availability sections and all ext-link elements
    text_parts: List[str] = []

    # Look for data availability statement
    for sec in article_elem.findall('.//sec'):
        sec_type = (sec.get('sec-type') or '').lower()
        title_el = sec.find('title')
        sec_title = (title_el.text or '').lower() if title_el is not None else ''
        if 'data' in sec_title or 'availability' in sec_title or sec_type == 'data-availability':
            text_parts.append(_elem_text(sec))

    # Also check back matter notes
    for notes in article_elem.findall('.//notes'):
        text_parts.append(_elem_text(notes))

    # Collect ext-link hrefs
    for link in article_elem.findall('.//{http://www.w3.org/1999/xlink}ext-link'):
        href = link.get('{http://www.w3.org/1999/xlink}href', '')
        if href:
            text_parts.append(href)
    for link in article_elem.findall('.//ext-link'):
        href = link.get('{http://www.w3.org/1999/xlink}href', link.text or '')
        if href:
            text_parts.append(href)

    full_text = ' '.join(text_parts)

    for pattern, repo, url_template in DATA_REPO_PATTERNS:
        for match in re.finditer(pattern, full_text):
            accession = match.group(0)
            key = (repo, accession)
            if key not in seen:
                seen.add(key)
                url = url_template.format(accession)
                data_sources.append(DataSource(repository=repo, accession=accession, url=url))

    return data_sources


def _elem_text(elem) -> str:
    """Recursively extract all text content from an XML element."""
    if elem is None:
        return ''
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_elem_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()
