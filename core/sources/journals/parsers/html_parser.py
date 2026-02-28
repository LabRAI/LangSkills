"""
Generic HTML parser for journal article pages.

Uses BeautifulSoup for robust extraction of figures, captions, and data availability.
Works as a fallback for journals not covered by specific parsers (Science, Cell, etc.).
"""
import re
from typing import List, Tuple

from core.sources.journals.models import DataSource, FigureInfo
from .pmc_parser import DATA_REPO_PATTERNS


def extract_figures_bs4(html: str = '', base_url: str = '') -> List[FigureInfo]:
    """Extract figures using BeautifulSoup (robust, handles messy HTML)."""
    if not html:
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    figures: List[FigureInfo] = []
    fig_idx = 0

    # Try <figure> elements first
    for fig_elem in soup.find_all('figure'):
        fig_idx += 1
        fig_id = fig_elem.get('id', f'fig{fig_idx}')

        # Caption
        caption = ''
        figcaption = fig_elem.find('figcaption')
        if figcaption:
            caption = re.sub(r'\s+', ' ', figcaption.get_text(' ', strip=True))

        # Image URL
        img = fig_elem.find('img')
        img_url = ''
        if img:
            img_url = img.get('data-src') or img.get('src') or ''
            if img_url and not img_url.startswith('http') and base_url:
                from urllib.parse import urljoin
                img_url = urljoin(base_url, img_url)

        fig_type = 'main'
        if 'supp' in fig_id.lower() or 'supplement' in caption.lower():
            fig_type = 'supplementary'
        elif 'extended' in fig_id.lower():
            fig_type = 'extended'

        figures.append(FigureInfo(
            figure_id=fig_id,
            caption=caption,
            full_size_url=img_url,
            figure_type=fig_type,
        ))

    # Fallback: look for divs with figure-related classes
    if not figures:
        for div in soup.find_all('div', class_=re.compile(r'fig|image', re.IGNORECASE)):
            fig_idx += 1
            img = div.find('img')
            if not img:
                continue
            img_url = img.get('data-src') or img.get('src') or ''
            if img_url and not img_url.startswith('http') and base_url:
                from urllib.parse import urljoin
                img_url = urljoin(base_url, img_url)
            caption = ''
            cap_elem = div.find(class_=re.compile(r'caption', re.IGNORECASE))
            if cap_elem:
                caption = re.sub(r'\s+', ' ', cap_elem.get_text(' ', strip=True))
            figures.append(FigureInfo(
                figure_id=f'fig{fig_idx}',
                caption=caption,
                full_size_url=img_url,
                figure_type='main',
            ))

    return figures


def extract_data_availability_bs4(html: str = '') -> List[DataSource]:
    """Extract data availability using BeautifulSoup."""
    if not html:
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    data_sources: List[DataSource] = []
    seen: set = set()

    # Look for data availability sections
    text_parts: List[str] = []
    for heading in soup.find_all(re.compile(r'^h[1-6]$', re.IGNORECASE)):
        heading_text = heading.get_text('', strip=True).lower()
        if 'data' in heading_text and ('availab' in heading_text or 'access' in heading_text):
            # Collect text from the following siblings until next heading
            sibling = heading.find_next_sibling()
            while sibling and not sibling.name or (sibling and not re.match(r'^h[1-6]$', sibling.name or '', re.IGNORECASE)):
                if sibling:
                    text_parts.append(sibling.get_text(' ', strip=True))
                    # Also collect href values
                    for a in sibling.find_all('a', href=True):
                        text_parts.append(a['href'])
                    sibling = sibling.find_next_sibling()
                else:
                    break

    # Also search for sections/divs with data-availability class or id
    for elem in soup.find_all(
        attrs={'class': re.compile(r'data.?avail', re.IGNORECASE)}
    ):
        text_parts.append(elem.get_text(' ', strip=True))
        for a in elem.find_all('a', href=True):
            text_parts.append(a['href'])

    for elem in soup.find_all(attrs={'id': re.compile(r'data.?avail', re.IGNORECASE)}):
        text_parts.append(elem.get_text(' ', strip=True))
        for a in elem.find_all('a', href=True):
            text_parts.append(a['href'])

    full_text = ' '.join(text_parts)

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


# Section heading patterns for fulltext extraction
_SECTION_PATTERNS = {
    'introduction': re.compile(r'\bintroduction\b', re.IGNORECASE),
    'methods': re.compile(r'\b(?:methods?|materials?\s+and\s+methods?|experimental)\b', re.IGNORECASE),
    'results': re.compile(r'\bresults?\b', re.IGNORECASE),
    'discussion': re.compile(r'\bdiscussion\b', re.IGNORECASE),
    'conclusion': re.compile(r'\bconclusion\b', re.IGNORECASE),
}


def extract_fulltext_sections_bs4(html: str = '') -> dict:
    """Extract fulltext sections (introduction, methods, results, discussion) from HTML."""
    if not html:
        return {}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    sections: dict = {}

    for heading in soup.find_all(re.compile(r'^h[1-6]$', re.IGNORECASE)):
        heading_text = heading.get_text(' ', strip=True)
        matched_key = None
        for key, pattern in _SECTION_PATTERNS.items():
            if pattern.search(heading_text):
                matched_key = key
                break
        if not matched_key:
            continue

        parts: List[str] = []
        sibling = heading.find_next_sibling()
        while sibling:
            if sibling.name and re.match(r'^h[1-6]$', sibling.name, re.IGNORECASE):
                break
            text = sibling.get_text(' ', strip=True)
            if text:
                parts.append(text)
            sibling = sibling.find_next_sibling()

        body = ' '.join(parts).strip()
        if body and (matched_key not in sections or len(body) > len(sections[matched_key])):
            sections[matched_key] = body

    return sections
