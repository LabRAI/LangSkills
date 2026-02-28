"""LangSkills (Python rewrite).

This package implements the LangSkills pipeline in Python.
The goal is readability and easier debugging rather than a 1:1 line-by-line translation.
"""

from .config import DOMAIN_CONFIG  # re-export for convenience

__all__ = ["DOMAIN_CONFIG"]
