Unsupported opcode: MAP_ADD (188)
Unsupported opcode: RETURN_GENERATOR (109)
# Source Generated with Decompyle++
# File: elife_parser.pyc (Python 3.12)

__doc__ = '\neLife parser — eLife REST API.\n\neLife is fully OA and has an excellent API.\nAPI docs: https://api.elifesciences.org\n'
import re
from typing import List, Tuple, Optional
from core.sources.journals.models import DataSource, FigureInfo, PaperRecord
from .pmc_parser import DATA_REPO_PATTERNS

def build_elife_search_url(page = None, per_page = None, year_from = None, subject = (1, 100, 2020, '', 'desc'), order = ('page', int, 'per_page', int, 'year_from', int, 'subject', str, 'order', str, 'return', str)):
    '''Build eLife API search URL.'''
    base = 'https://api.elifesciences.org/search'
    params = {
        'for': '',
        'page': str(page),
        'per-page': str(per_page),
        'sort': 'date',
        'order': order,
        'type[]': 'research-article',
        'start-date': f'''{year_from}-01-01''',
        'end-date': '2026-12-31' }
    if subject:
        params['subject[]'] = subject
    param_str = (lambda .0: pass# WARNING: Decompyle incomplete
)(params.items()())
    return f'''{base}?{param_str}'''


def build_elife_article_url(article_id = None):
    '''Build URL to fetch full article JSON from eLife API.'''
    return f'''https://api.elifesciences.org/articles/{article_id}'''


def parse_elife_search_response(json_data = None):
    '''Parse eLife search response. Returns (items, total).'''
    items = json_data.get('items', [])
    total = json_data.get('total', 0)
    return (items, total)


def elife_item_to_paper_stub(item = None):
    '''Convert an eLife search result item to a PaperRecord stub (no figures yet).'''
    article_id = item.get('id', '')
    if not article_id:
        return None
    doi = item.get('doi', f'''10.7554/eLife.{article_id}''')
    title = item.get('title', '')
    pub_date = item.get('published', '')[:10]
    authors = []
    for a in item.get('authors', []):
        name = a.get('name', { })
        if isinstance(name, dict):
            preferred = name.get('preferred', '')
            if not preferred:
                continue
            authors.append(preferred)
            continue
        if not isinstance(name, str):
            continue
        authors.append(name)
    return PaperRecord(doi = doi, title = title, journal = 'eLife', journal_family = 'eLife', authors = authors, pub_date = pub_date, url = f'''https://elifesciences.org/articles/{article_id}''', is_open_access = True)

# WARNING: Decompyle incomplete
