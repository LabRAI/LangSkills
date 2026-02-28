# Source Generated with Decompyle++
# File: __init__.pyc (Python 3.12)

'''Journal pipeline subpackage.

`langskills journal-pipeline` crawls open-access journal articles (via PMC / PLOS /
eLife / Springer) and turns each paper into a reproducible, auditable skill
package that focuses on figure + open-data link extraction.
'''
from __future__ import annotations

def cli_journal_pipeline(argv = None):
    _impl = cli_journal_pipeline
    from . import cli
    return int(_impl(argv))

__all__ = [
    'cli_journal_pipeline']
