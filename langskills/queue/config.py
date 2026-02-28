from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.paths import repo_root


def _env_value(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        raw = os.environ.get(f"LANGSKILLS_{name}")
    if raw is None:
        return str(default)
    return str(raw)


def _env_int(name: str, default: int) -> int:
    raw = _env_value(name, "").strip()
    try:
        return int(raw) if raw else int(default)
    except Exception:
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_value(name, "").strip().lower()
    if raw == "":
        return bool(default)
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return bool(default)


def _parse_kv_int_map(raw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    s = str(raw or "").strip()
    if not s:
        return out
    for chunk in s.split(","):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        try:
            out[key] = int(val)
        except Exception:
            continue
    return out


@dataclass
class QueueSettings:
    backend: str
    path: Path
    max_attempts: int
    lease_seconds: int
    backoff_base_seconds: int
    backoff_max_seconds: int
    concurrency_global: int
    concurrency_per_source_type: dict[str, int]
    llm_rate_limit_rps: float
    llm_max_concurrency: int
    enable_improve_stage: bool
    enable_publish_stage: bool
    github_repo_fanout_n: int
    github_repo_fanout_select: str
    github_repo_fanout_max_file_bytes: int
    github_repo_fanout_prompt_max_files: int

    @classmethod
    def from_env(cls, *, repo_root_path: Path | None = None, overrides: dict[str, Any] | None = None) -> "QueueSettings":
        root = repo_root_path or repo_root()
        backend = str(_env_value("QUEUE_BACKEND", "sqlite") or "sqlite").strip().lower()
        path_raw = str(_env_value("QUEUE_PATH", str(root / "runs" / "queue.db")) or "").strip()
        path = Path(path_raw) if path_raw else Path(root / "runs" / "queue.db")
        if not path.is_absolute():
            path = (root / path).resolve()
        max_attempts = max(1, _env_int("QUEUE_MAX_ATTEMPTS", 5))
        lease_seconds = max(10, _env_int("QUEUE_LEASE_SECONDS", 600))
        backoff_base_seconds = max(1, _env_int("QUEUE_BACKOFF_BASE_SECONDS", 60))
        backoff_max_seconds = max(backoff_base_seconds, _env_int("QUEUE_BACKOFF_MAX_SECONDS", 600))
        concurrency_global = max(1, _env_int("QUEUE_CONCURRENCY_GLOBAL", 1))
        concurrency_per_source_type = _parse_kv_int_map(_env_value("QUEUE_CONCURRENCY_PER_SOURCE_TYPE", ""))
        llm_rate_limit_rps = 0.0
        try:
            llm_rate_limit_rps = float(str(_env_value("LLM_RATE_LIMIT_RPS", "") or "").strip() or 0.0)
        except Exception:
            llm_rate_limit_rps = 0.0
        llm_max_concurrency = max(1, _env_int("LLM_MAX_CONCURRENCY", 1))
        enable_improve_stage = _env_bool("QUEUE_ENABLE_IMPROVE_STAGE", True)
        enable_publish_stage = _env_bool("QUEUE_ENABLE_PUBLISH_STAGE", True)
        github_repo_fanout_n = max(0, _env_int("GITHUB_REPO_FANOUT_N", 0))
        github_repo_fanout_select = str(_env_value("GITHUB_REPO_FANOUT_SELECT", "heuristic") or "heuristic").strip().lower()
        if github_repo_fanout_select not in {"heuristic", "llm"}:
            github_repo_fanout_select = "heuristic"
        github_repo_fanout_max_file_bytes = max(1, _env_int("GITHUB_REPO_FANOUT_MAX_FILE_BYTES", 80_000))
        github_repo_fanout_prompt_max_files = max(1, _env_int("GITHUB_REPO_FANOUT_PROMPT_MAX_FILES", 300))

        if overrides:
            if "backend" in overrides:
                backend = str(overrides.get("backend") or backend).strip().lower()
            if "path" in overrides and overrides.get("path"):
                path = Path(str(overrides.get("path")))
            if "max_attempts" in overrides:
                max_attempts = int(overrides.get("max_attempts") or max_attempts)
            if "lease_seconds" in overrides:
                lease_seconds = int(overrides.get("lease_seconds") or lease_seconds)
            if "backoff_base_seconds" in overrides:
                backoff_base_seconds = int(overrides.get("backoff_base_seconds") or backoff_base_seconds)
            if "backoff_max_seconds" in overrides:
                backoff_max_seconds = int(overrides.get("backoff_max_seconds") or backoff_max_seconds)
            if "concurrency_global" in overrides:
                concurrency_global = int(overrides.get("concurrency_global") or concurrency_global)
            if "concurrency_per_source_type" in overrides:
                v = overrides.get("concurrency_per_source_type")
                if isinstance(v, dict):
                    concurrency_per_source_type = {str(k): int(vv) for k, vv in v.items()}
            if "llm_rate_limit_rps" in overrides:
                llm_rate_limit_rps = float(overrides.get("llm_rate_limit_rps") or llm_rate_limit_rps)
            if "llm_max_concurrency" in overrides:
                llm_max_concurrency = int(overrides.get("llm_max_concurrency") or llm_max_concurrency)
            if "enable_improve_stage" in overrides:
                enable_improve_stage = bool(overrides.get("enable_improve_stage"))
            if "enable_publish_stage" in overrides:
                enable_publish_stage = bool(overrides.get("enable_publish_stage"))
            if "github_repo_fanout_n" in overrides:
                github_repo_fanout_n = int(overrides.get("github_repo_fanout_n") or github_repo_fanout_n)
            if "github_repo_fanout_select" in overrides:
                github_repo_fanout_select = str(overrides.get("github_repo_fanout_select") or github_repo_fanout_select).strip().lower()
                if github_repo_fanout_select not in {"heuristic", "llm"}:
                    github_repo_fanout_select = "heuristic"
            if "github_repo_fanout_max_file_bytes" in overrides:
                github_repo_fanout_max_file_bytes = int(overrides.get("github_repo_fanout_max_file_bytes") or github_repo_fanout_max_file_bytes)
            if "github_repo_fanout_prompt_max_files" in overrides:
                github_repo_fanout_prompt_max_files = int(overrides.get("github_repo_fanout_prompt_max_files") or github_repo_fanout_prompt_max_files)

        return cls(
            backend=backend,
            path=path,
            max_attempts=max_attempts,
            lease_seconds=lease_seconds,
            backoff_base_seconds=backoff_base_seconds,
            backoff_max_seconds=backoff_max_seconds,
            concurrency_global=concurrency_global,
            concurrency_per_source_type=concurrency_per_source_type,
            llm_rate_limit_rps=llm_rate_limit_rps,
            llm_max_concurrency=llm_max_concurrency,
            enable_improve_stage=enable_improve_stage,
            enable_publish_stage=enable_publish_stage,
            github_repo_fanout_n=github_repo_fanout_n,
            github_repo_fanout_select=github_repo_fanout_select,
            github_repo_fanout_max_file_bytes=github_repo_fanout_max_file_bytes,
            github_repo_fanout_prompt_max_files=github_repo_fanout_prompt_max_files,
        )
