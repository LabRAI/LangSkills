
'''Article discovery from various APIs.'''
import logging
from typing import List
from core.sources.journals.models import PaperRecord
from core.sources.journals.parsers.pmc_parser import build_esearch_url, parse_esearch_response
from core.sources.journals.parsers.nature_parser import build_springer_api_url, parse_springer_api_response, springer_record_to_paper
from core.sources.journals.parsers.plos_parser import build_plos_search_url, parse_plos_search_response, plos_doc_to_paper
from core.sources.journals.parsers.elife_parser import build_elife_search_url, parse_elife_search_response, elife_item_to_paper_stub
from .config import CrawlConfig
from .http_client import AsyncHTTPClient
logger = logging.getLogger('science_crawler')

class ArticleDiscovery:
    '''Discover article DOIs/IDs from various APIs.'''
    
    def __init__(self = None, client = None, config = None):
        self.client = client
        self.config = config

    
    async def discover_pmc_articles(self = None, issn = None, journal_name = None, max_results = ('', '', 500)):
        '''Discover PMC IDs via NCBI E-utilities.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def discover_springer_articles(self = None, issn = None, max_results = None):
        '''Discover articles via Springer Nature API.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def discover_plos_articles(self = None, journal_slug = None, max_results = None):
        '''Discover articles via PLOS Search API.'''
        pass
    # WARNING: Decompyle incomplete

    
    async def discover_elife_articles(self = None, max_results = None):
        '''Discover articles via eLife API.'''
        pass
    # WARNING: Decompyle incomplete


