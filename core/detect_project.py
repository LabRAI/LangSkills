"""Detect project type by scanning directory file patterns.

Returns a list of matching domain names sorted by relevance,
used by ``bundle-install --auto`` to download only relevant bundles.
"""

from __future__ import annotations

import os
from pathlib import Path


def _has_any(root: Path, names: list[str]) -> bool:
    """Check if any of the given filenames exist directly under *root*."""
    for n in names:
        if (root / n).exists():
            return True
    return False


def _has_glob(root: Path, pattern: str) -> bool:
    """Check if at least one file matches a glob pattern under *root*."""
    try:
        return next(root.glob(pattern), None) is not None
    except (OSError, StopIteration):
        return False


def _requirements_contains(root: Path, keywords: list[str]) -> bool:
    """Check if requirements.txt contains any of the given keywords."""
    req = root / "requirements.txt"
    if not req.exists():
        return False
    try:
        text = req.read_text(encoding="utf-8").lower()
        return any(kw in text for kw in keywords)
    except Exception:
        return False


def detect_domains(project_dir: Path | None = None) -> list[str]:
    """Return domain names sorted by relevance for the given project directory.

    Scans file patterns to determine which technology domains are relevant.
    A project can match multiple domains (e.g. ``["web", "devtools"]``).

    Parameters
    ----------
    project_dir : Path, optional
        Directory to scan. Defaults to the current working directory.

    Returns
    -------
    list[str]
        Domain names such as ``"web"``, ``"linux"``, ``"ml"``, etc.
    """
    root = Path(project_dir) if project_dir else Path.cwd()
    if not root.is_dir():
        return []

    domains: list[str] = []

    # web
    if _has_any(root, ["package.json", "tsconfig.json"]) or \
       _has_glob(root, "*.tsx") or _has_glob(root, "*.jsx") or \
       _has_glob(root, "next.config.*") or _has_glob(root, "vite.config.*") or \
       _has_glob(root, "nuxt.config.*") or _has_any(root, ["angular.json"]):
        domains.append("web")

    # ml
    if _requirements_contains(root, ["torch", "tensorflow", "transformers", "keras", "jax"]):
        domains.append("ml")

    # llm
    if _requirements_contains(root, ["langchain", "openai", "llama", "anthropic", "llamaindex"]):
        domains.append("llm")

    # programming (general Python/Ruby/Go/Rust/Java)
    if _has_any(root, ["setup.py", "pyproject.toml", "Gemfile", "go.mod",
                        "Cargo.toml", "pom.xml", "build.gradle"]):
        # Only add if not already covered by a more specific domain
        if "ml" not in domains and "llm" not in domains:
            domains.append("programming")
    elif _has_any(root, ["requirements.txt"]) and "ml" not in domains and "llm" not in domains:
        domains.append("programming")

    # cloud
    if _has_any(root, ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]) or \
       _has_glob(root, "k8s/**") or _has_glob(root, "helm/**") or \
       _has_any(root, ["terraform.tf", "serverless.yml"]):
        domains.append("cloud")

    # linux
    if _has_any(root, ["Makefile", "CMakeLists.txt"]) or \
       _has_glob(root, "*.c") or _has_glob(root, "*.h") or \
       _has_glob(root, "**/*.c"):
        domains.append("linux")

    # devtools
    if _has_glob(root, ".github/workflows/*.yml") or \
       _has_glob(root, ".github/workflows/*.yaml") or \
       _has_any(root, ["Jenkinsfile", ".gitlab-ci.yml", ".circleci"]):
        domains.append("devtools")

    # observability
    if _has_any(root, ["prometheus.yml", "prometheus.yaml"]) or \
       _has_glob(root, "grafana/**") or \
       _requirements_contains(root, ["prometheus", "grafana", "datadog"]):
        domains.append("observability")

    # data
    if _has_glob(root, "*.sql") or _has_any(root, ["dbt_project.yml"]) or \
       _requirements_contains(root, ["pandas", "pyspark", "dbt"]):
        domains.append("data")

    # security
    if _requirements_contains(root, ["cryptography", "paramiko", "scapy"]) or \
       _has_glob(root, "*.rules") or _has_any(root, ["snort.conf", "suricata.yaml"]):
        domains.append("security")

    # research
    if _has_glob(root, "*.bib") or _has_glob(root, "*.tex") or \
       _has_glob(root, "**/*.bib") or _has_glob(root, "**/*.tex"):
        domains.append("research")

    return domains
