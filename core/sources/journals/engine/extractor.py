Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: PUSH_EXC_INFO (105)
# Source Generated with Decompyle++
# File: extractor.pyc (Python 3.12)

'''Content extraction: fetch article HTML/XML and extract figures + data links.'''
import re
import logging
from typing import List
from core.sources.journals.models import PaperRecord
from core.sources.journals.parsers.pmc_parser import build_efetch_url, parse_efetch_xml
from core.sources.journals.parsers.nature_parser import parse_nature_article_html
from core.sources.journals.parsers.plos_parser import extract_plos_figures_from_html, extract_plos_data_from_html, _doi_to_plos_slug
from core.sources.journals.parsers.elife_parser import build_elife_article_url, parse_elife_article_json
from core.sources.journals.parsers.html_parser import extract_figures_bs4, extract_data_availability_bs4, extract_fulltext_sections_bs4
from .config import CrawlConfig
from .http_client import AsyncHTTPClient
logger = logging.getLogger('science_crawler')

class ContentExtractor:
    '''Fetch article HTML/XML and extract figures + data links.'''
    
    def __init__(self = None, client = None, config = None):
        self.client = client
        self.config = config

    
    async def enrich_paper_via_pmc(self = None, pmc_ids = None, family_name = None):
        '''Fetch full XML from PMC and parse into PaperRecords with figures and data.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def enrich_nature_paper(self = None, paper = None):
        '''Fetch Nature article HTML and extract figures + data + fulltext sections.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def enrich_plos_paper(self = None, paper = None):
        '''Enrich PLOS paper with figures, data, and fulltext sections from article HTML.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def enrich_elife_paper(self = None, paper = None):
        '''Enrich eLife paper with figures and data from the API.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def enrich_generic_paper(self = None, paper = None):
        '''Generic enrichment: fetch article HTML and extract with BS4.'''
        pass
    # WARNING: Decompyle incomplete

    _merge_html_sections = (lambda paper = None, html = None: html_secs = extract_fulltext_sections_bs4(html)if not html_secs:
Noneif not paper.fulltext_sections:
paper.fulltext_sections = { }for k, v in html_secs.items():
if not k not in paper.fulltext_sections and len(v) > len(paper.fulltext_sections.get(k, '')):
continuepaper.fulltext_sections[k] = vNone# WARNING: Decompyle incomplete
)()

