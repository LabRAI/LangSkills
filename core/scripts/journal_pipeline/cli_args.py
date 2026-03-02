# Source Generated with Decompyle++
# File: cli_args.pyc (Python 3.12)

from __future__ import annotations
import argparse

def parse_journal_pipeline_args(argv = None):
    parser = argparse.ArgumentParser(prog = 'langskills-rai journal-pipeline')
    parser.add_argument('--max-papers', '-n', type = int, default = 10000)
    parser.add_argument('--families', '-f', nargs = '+', default = None, choices = [
        'Nature',
        'Science',
        'Cell',
        'PLOS',
        'eLife',
        'PMC',
        'Other'], help = 'Journal families to crawl (default: all)')
    parser.add_argument('--concurrency', '-c', type = int, default = 20, help = 'Max concurrent HTTP requests')
    parser.add_argument('--download-concurrency', type = int, default = 30, help = 'Max concurrent image downloads')
    parser.add_argument('--delay', type = float, default = 0.5, help = 'Per-domain delay in seconds')
    parser.add_argument('--no-download', action = 'store_true', help = 'Skip downloading figure images (metadata only)')
    parser.add_argument('--year-from', type = int, default = 2020)
    parser.add_argument('--year-to', type = int, default = 2026)
    parser.add_argument('--springer-key', default = '', help = 'Springer Nature API key (or SPRINGER_API_KEY env var)')
    parser.add_argument('--ncbi-key', default = '', help = 'NCBI API key (or NCBI_API_KEY env var)')
    parser.add_argument('--profile', default = 'research', help = 'Skills profile/domain to write under run_dir/skills/')
    parser.add_argument('--skill-kind', default = 'journal_figure_data_mining')
    parser.add_argument('--llm-skills', action = 'store_true', help = 'Generate additional LLM paper skills (paper.idea_intro/experiment/picture/method)')
    parser.add_argument('--llm-only', action = 'store_true', help = 'Only generate skills via LLM (skip deterministic baseline journal extraction skill). Requires --llm-skills.')
    parser.add_argument('--max-skills-per-paper', type = int, default = 3, help = 'Max LLM paper skills per paper (includes idea+intro)')
    parser.add_argument('--llm-concurrency', type = int, default = 4, help = 'Max concurrent LLM calls for --llm-skills')
    parser.add_argument('--provider', default = None, help = 'LLM provider override for --llm-skills (openai/ollama/mock)')
    parser.add_argument('--dry-run', action = 'store_true', help = 'Write manifest and exit (no network)')
    parser.add_argument('--publish', action = 'store_true')
    parser.add_argument('--publish-overwrite', action = 'store_true')
    parser.add_argument('--publish-allow-needs-review', action = 'store_true')
    parser.add_argument('--verbose', action = 'store_true')
    return parser.parse_args(argv)

