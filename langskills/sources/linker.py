from __future__ import annotations

import re


def extract_github_urls_from_text(text: str) -> list[str]:
    urls = re.findall(r"https?://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", str(text or ""))
    return list(dict.fromkeys(urls))

def link_github_repos_from_paper_entry(entry: dict) -> list[str]:
    """
    Heuristics:
    1) Pull github.com URLs from title/summary/comment-like fields.
    """
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("summary") or ""),
            str(entry.get("comment") or ""),
            str(entry.get("full_text") or ""),
            str(entry.get("body") or ""),
            str(entry.get("content") or ""),
        ]
    )
    urls = extract_github_urls_from_text(text)
    return urls or []
