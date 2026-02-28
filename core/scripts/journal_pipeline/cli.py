Unsupported opcode: PUSH_EXC_INFO (105)
# Source Generated with Decompyle++
# File: cli.pyc (Python 3.12)

from __future__ import annotations
import asyncio
import concurrent.futures as concurrent
import json
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from core.env import load_dotenv
try:
    from core.scripts.validate_skills.core import validate_skills
except ImportError:
    validate_skills = None
from core.skills.publish import publish_run_to_skills_library
from core.sources.artifacts import write_source_artifact
from core.sources.journals.engine import CrawlConfig, CrawlStats, crawl_journals
from core.sources.journals.normalize import paper_primary_url, paper_to_extracted_text, paper_to_raw_json
from core.utils.fs import ensure_dir, make_run_dir, write_json_atomic
from core.utils.paths import repo_root as _repo_root
from core.utils.time import utc_now_iso_z
from .cli_args import parse_journal_pipeline_args
_PAPER_SKILL_KINDS = [
    'paper.idea_intro',
    'paper.experiment',
    'paper.picture',
    'paper.method']

def _env_int(name = None, default = None):
    if not os.environ.get(name):
        os.environ.get(name)
    raw = str('').strip()
    if raw:
        return int(raw)
    return None(default)
# WARNING: Decompyle incomplete


def _truncate(text = None, max_len = None):
    if not text:
        text
    s = str('')
    if max_len <= 0:
        return s
    if None(s) <= max_len:
        return s
    return None[:max(0, max_len - 1)] + '…'


def _infer_journal_license(*, paper):
    if not getattr(paper, 'journal_family', ''):
        getattr(paper, 'journal_family', '')
    family = str('').strip().lower()
    is_oa = bool(getattr(paper, 'is_open_access', True))
    if family == 'plos' and is_oa:
        return ('CC-BY-4.0', 'low')
    return ('', 'unknown')


def _sanitize_paper_extra_for_llm(extra = None):
    figures_in = extra.get('figures') if isinstance(extra.get('figures'), list) else []
    figures = []
    for f in figures_in[:12]:
        if not isinstance(f, dict):
            continue
        if not f.get('figure_id'):
            f.get('figure_id')
        if not f.get('caption'):
            f.get('caption')
        if not f.get('local_path'):
            f.get('local_path')
        if not f.get('panel_label'):
            f.get('panel_label')
        if not f.get('figure_type'):
            f.get('figure_type')
        figures.append({
            'figure_id': str('').strip(),
            'caption': _truncate(str('').strip(), 420),
            'local_path': str('').strip(),
            'panel_label': str('').strip(),
            'figure_type': str('').strip() })
    data_in = extra.get('data_sources') if isinstance(extra.get('data_sources'), list) else []
    data_sources = []
    for d in data_in[:12]:
        if not isinstance(d, dict):
            continue
        if not d.get('repository'):
            d.get('repository')
        if not d.get('accession'):
            d.get('accession')
        if not d.get('description'):
            d.get('description')
        if not d.get('data_type'):
            d.get('data_type')
        data_sources.append({
            'repository': str('').strip(),
            'accession': str('').strip(),
            'description': _truncate(str('').strip(), 280),
            'data_type': str('').strip() })
    if not extra.get('abstract'):
        extra.get('abstract')
    abstract = str('').strip()
    ft_raw = extra.get('fulltext_sections') if isinstance(extra.get('fulltext_sections'), dict) else { }
    fulltext_sections = { }
    for sec_key in ('introduction', 'methods', 'results', 'discussion'):
        if not ft_raw.get(sec_key):
            ft_raw.get(sec_key)
        val = str('').strip()
        if not val:
            continue
        max_c = {
            'introduction': 1200,
            'methods': 1800,
            'results': 1500,
            'discussion': 1000 }.get(sec_key, 1200)
        fulltext_sections[sec_key] = _truncate(val, max_c)
    return {
        'paper_abstract': _truncate(abstract, 1800),
        'paper_figures': figures,
        'paper_data_sources': data_sources,
        'paper_has_figures': bool(figures)Unsupported opcode: MAKE_CELL (225)
Unsupported opcode: MAP_ADD (188)
Unsupported opcode: MAKE_CELL (225)
,
        'paper_has_data_sources': bool(data_sources),
        'paper_fulltext_sections': fulltext_sections,
        'paper_has_fulltext': bool(fulltext_sections) }


def _paper_extra(paper = None, *, run_dir):
    pass
# WARNING: Decompyle incomplete


def _write_manifest(*, run_dir, ns, stats, total_sources, llm):
    pass
# WARNING: Decompyle incomplete


def cli_journal_pipeline(argv = None):
    pass
# WARNING: Decompyle incomplete

