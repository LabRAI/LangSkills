from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CrawlConfig:
    output_dir: str = "output"
    max_papers: int = 10000
    families: Optional[List[str]] = None
    max_concurrent_requests: int = 20
    max_concurrent_downloads: int = 30
    per_domain_delay: float = 0.5
