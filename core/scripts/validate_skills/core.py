"""Skill validation orchestrator."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from ...config import read_license_policy, read_quality_gates
from ...utils.fs import list_skill_dirs
from ...utils.paths import repo_root as _repo_root
from .core_checks import validate_skill_dir


def validate_skills(
    *,
    repo_root: Path | str | None = None,
    root: Path | str | None = None,
    strict: bool = False,
    check_package: bool = False,
    max_skills: int | None = 0,
) -> tuple[list[str], list[str]]:
    """Validate all skill directories under *root*.

    Returns (errors, warnings).
    """
    rr = Path(repo_root or _repo_root()).resolve()
    skills_root = Path(root or (rr / "skills" / "by-skill")).resolve()

    if not skills_root.exists():
        return ([], [f"skills root does not exist: {skills_root}"])

    dirs = list_skill_dirs(skills_root)
    if max_skills and max_skills > 0:
        dirs = dirs[:max_skills]

    policy = read_license_policy(rr)
    gates = read_quality_gates(rr)
    requirements = gates.get("requirements") if isinstance(gates.get("requirements"), dict) else {}

    require_evidence = bool(requirements.get("evidence_required", True))
    require_verification = bool(requirements.get("verification_required", True))
    require_skill_kind = bool(requirements.get("require_skill_kind", False))
    min_code_blocks = int(requirements.get("min_code_blocks", 1))
    max_steps = int(requirements.get("max_steps", 12))

    errors: list[str] = []
    warnings: list[str] = []

    for d in dirs:
        try:
            rel = str(d.relative_to(skills_root))
        except ValueError:
            rel = str(d)

        validate_skill_dir(
            d=d,
            repo_root=rr,
            rel=rel,
            policy=policy,
            strict=strict,
            check_package=check_package,
            require_evidence=require_evidence,
            require_skill_kind=require_skill_kind,
            require_verification=require_verification,
            min_code_blocks=min_code_blocks,
            max_steps=max_steps,
            errors=errors,
            warnings=warnings,
        )

    return errors, warnings


def cli_validate_skills(args: argparse.Namespace) -> int:
    """CLI entry point for validate command."""
    root = getattr(args, "root", None)
    strict = bool(getattr(args, "strict", False))
    check_package = bool(getattr(args, "package", False))
    max_skills = int(getattr(args, "max_skills", 0) or 0)

    errors, warnings = validate_skills(
        root=root,
        strict=strict,
        check_package=check_package,
        max_skills=max_skills,
    )

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        print(f"\nValidation FAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1

    print(f"\nValidation PASSED: 0 errors, {len(warnings)} warnings")
    return 0
