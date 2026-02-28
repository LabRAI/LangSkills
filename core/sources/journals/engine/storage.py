
'''Data storage: save crawled data to disk.'''
import json
import os
from datetime import datetime
from typing import Set
from core.sources.journals.models import PaperRecord
from .config import CrawlConfig

class DataStorage:
    '''Save crawled data to disk in organized format.'''
    
    def __init__(self = None, config = None):
        self.config = config
        self.metadata_dir = os.path.join(config.output_dir, 'metadata')
        self.index_path = os.path.join(config.output_dir, 'index.jsonl')
        os.makedirs(self.metadata_dir, exist_ok = True)

    
    def save_paper(self = None, paper = None):
        '''Save a single paper record as JSON.'''
        paper.crawled_at = datetime.now().isoformat()
        safe_doi = paper.doi.replace('/', '_').replace(':', '_')
        path = os.path.join(self.metadata_dir, f'''{safe_doi}.json''')
    # WARNING: Decompyle incomplete

    
    def get_existing_dois(self = None):
        '''Load already-crawled DOIs for resume support.'''
        existing = set()
    # WARNING: Decompyle incomplete

    
    def save_summary(self = None, stats = None):
        '''Save a crawl summary.'''
        path = os.path.join(self.config.output_dir, 'crawl_summary.json')
    # WARNING: Decompyle incomplete


