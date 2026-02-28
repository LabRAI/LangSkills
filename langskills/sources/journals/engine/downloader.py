Unsupported opcode: RETURN_GENERATOR (109)
# Source Generated with Decompyle++
# File: downloader.pyc (Python 3.12)

'''Figure image downloader.'''
import os
from langskills.sources.journals.models import PaperRecord
from .config import CrawlConfig
from .http_client import AsyncHTTPClient
from langskills.utils.hashing import slugify

def _guess_extension(url = None):
    '''Guess file extension from URL.'''
    if not url:
        url
    raw = str('')
    lower = raw.lower()
    if 'journals.plos.org' in lower and '/article/figure/image' in lower:
        if 'size=original' in lower:
            return '.tiff'
        return '.png'
    url_lower = lower.split('?')[0]
    for ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.svg', '.gif', '.webp', '.pdf'):
        if not url_lower.endswith(ext):
            continue
        
        return ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.svg', '.gif', '.webp', '.pdf'), ext
    return '.jpg'


class FigureDownloader:
    '''Download figure images concurrently.'''
    
    def __init__(self = None, client = None, config = None):
        self.client = client
        self.config = config

    
    async def download_paper_figures(self = None, paper = None):
        '''Download all figures for a paper.'''
        pass
    # WARNING: Decompyle incomplete


