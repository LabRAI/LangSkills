Something TERRIBLE happened!
Something TERRIBLE happened!
Unsupported opcode: MAP_ADD (188)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: RETURN_GENERATOR (109)
Unsupported opcode: POP_JUMP_IF_NOT_NONE (238)
# Source Generated with Decompyle++
# File: pmc_parser.pyc (Python 3.12)

__doc__ = '\nPMC (PubMed Central) parser — the universal backbone.\n\nMost OA articles from Nature, Science, Cell, PLOS, etc. are deposited in PMC.\nWe use the NCBI E-utilities API (esearch + efetch) to:\n  1. Search for OA articles by journal ISSN\n  2. Fetch full XML (PMC OA subset)\n  3. Extract figures, captions, and data-availability statements\n'
import re

ElementTree
from typing import List, Optional, Tuple
Optional = Optional
Tuple = Tuple
import xml.etree.ElementTree, etree
from core.sources.journals.models import DataSource, FigureInfo, PaperRecord
DATA_REPO_PATTERNS = [
    ('GSE\\d{4,8}', 'GEO', 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={}'),
    ('GSM\\d{4,8}', 'GEO', 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={}'),
    ('(?:SRP|SRR|SRX|SRS|PRJNA)\\d{4,10}', 'SRA', 'https://www.ncbi.nlm.nih.gov/sra/{}'),
    ('PRJNA\\d{4,10}', 'BioProject', 'https://www.ncbi.nlm.nih.gov/bioproject/{}'),
    ('E-[A-Z]{4}-\\d{1,8}', 'ArrayExpress', 'https://www.ebi.ac.uk/arrayexpress/experiments/{}'),
    ('\\b[0-9][A-Za-z0-9]{3}\\b', 'PDB', 'https://www.rcsb.org/structure/{}'),
    ('10\\.5281/zenodo\\.\\d+', 'Zenodo', 'https://doi.org/{}'),
    ('10\\.6084/m9\\.figshare\\.\\d+', 'Figshare', 'https://doi.org/{}'),
    ('10\\.5061/dryad\\.[a-z0-9]+', 'Dryad', 'https://doi.org/{}'),
    ('github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'GitHub', 'https://{}'),
    ('EMD-\\d{4,6}', 'EMDB', 'https://www.ebi.ac.uk/emdb/{}'),
    ('[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}', 'UniProt', 'https://www.uniprot.org/uniprot/{}'),
    ('(?:ERR|ERX|ERS|ERA|ERP)\\d{6,10}', 'ENA', 'https://www.ebi.ac.uk/ena/browser/view/{}'),
    ('phs\\d{6}', 'dbGaP', 'https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id={}'),
    ('PXD\\d{6}', 'PRIDE', 'https://www.ebi.ac.uk/pride/archive/projects/{}'),
    ('MTBLS\\d+', 'MetaboLights', 'https://www.ebi.ac.uk/metabolights/{}')]

def build_esearch_url(issn, journal_name, retmax = None, retstart = None, min_date = None, max_date = ('', '', 500, 0, '2020/01/01', '2026/12/31', ''), api_key = ('issn', str, 'journal_name', str, 'retmax', int, 'retstart', int, 'min_date', str, 'max_date', str, 'api_key', str, 'return', str)):
    '''Build an E-utilities esearch URL for PMC OA articles.'''
    base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    parts = [
        'open access[filter]']
    if issn:
        parts.append(f'''{issn}[journal]''')
    elif journal_name:
        parts.append(f'''"{journal_name}"[journal]''')
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
        'usehistory': 'y' }
    if api_key:
        params['api_key'] = api_key
    param_str = (lambda .0: pass# WARNING: Decompyle incomplete
)(params.items()())
    return f'''{base}?{param_str}'''


def build_efetch_url(pmc_ids = None, api_key = None):
    '''Build an E-utilities efetch URL to get full XML for a batch of PMC IDs.'''
    base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    id_str = ','.join(pmc_ids)
    params = {
        'db': 'pmc',
        'id': id_str,
        'retmode': 'xml' }
    if api_key:
        params['api_key'] = api_key
    param_str = (lambda .0: pass# WARNING: Decompyle incomplete
)(params.items()())
    return f'''{base}?{param_str}'''


def parse_esearch_response(json_data = None):
    '''Parse esearch JSON response. Returns (list_of_pmc_ids, total_count).'''
    result = json_data.get('esearchresult', { })
    id_list = result.get('idlist', [])
    total = int(result.get('count', 0))
    return (id_list, total)


def parse_article_xml(article_elem = None):
    '''Parse a single <article> element from PMC efetch XML into a PaperRecord.'''
    front = article_elem.find('.//front')
# WARNING: Decompyle incomplete

# WARNING: Decompyle incomplete
