"""LangSkills (Python rewrite).

This package implements the LangSkills pipeline in Python.
The goal is readability and easier debugging rather than a 1:1 line-by-line translation.
"""

from .config import DOMAIN_CONFIG  # re-export for convenience

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.1.0"  # fallback when not installed via setuptools-scm

__all__ = ["DOMAIN_CONFIG", "__version__"]
