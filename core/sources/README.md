# `langskills/sources/`

Source discovery and fetching: turns URLs (or search results) into extracted text + evidence artifacts.

## Responsibilities

- Discover candidate URLs from different providers (web search aggregators, GitHub search, StackOverflow, arXiv, etc.).
- Fetch and extract text from each source type.
- Write auditable evidence artifacts to `captures/<run-id>/sources/<source_id>.json`.
- Optionally write a reusable global cache under `sources/by-id/<source_id>/`.

## Key files

- `router.py`: routes a URL to the correct fetcher based on source type.
- `artifacts.py`: defines and writes the `sources/<source_id>.json` evidence artifact.
- Fetchers:
  - `webpage.py`: plain webpage fetch + extraction
  - `github.py`: GitHub repo discovery/fanout + extraction
  - `stackoverflow.py`: StackOverflow (forum) search + extraction
  - `arxiv.py`: arXiv search + extraction
  - `zhihu.py`, `xhs.py`: Playwright-backed providers (often require login)
  - `baidu.py`: Baidu search helper
- `web_search.py`: aggregator for search providers (e.g., Tavily/Baidu/Zhihu/XHS).
- `playwright_utils.py`: shared Playwright helpers (cookies/login/session state, verification detection).
- `store.py`: writes the `sources/by-id/` cache.
- `types.py`: shared types.

## Playwright notes

Some providers require Playwright and browser install:

```bash
python3 -m playwright install chromium
```

See the root README for environment variables and login helpers: `../../README.md`.

