from __future__ import annotations

import os
from pathlib import Path
import json


def resolve_runtime_config_path(repo_root: Path) -> Path:
    override = str(os.environ.get("LANGSKILLS_CONFIG") or "").strip()
    if not override:
        override = str(os.environ.get("LANGSKILLS_RUNTIME_CONFIG") or "").strip()
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = repo_root / p
        return p
    # Unified config only.
    return repo_root / "config" / "langskills.json"


def load_runtime_env(repo_root: Path) -> dict[str, str]:
    path = resolve_runtime_config_path(repo_root)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    env_block = parsed.get("env") if isinstance(parsed, dict) else None
    if env_block is None and isinstance(parsed, dict):
        env_block = parsed
    if not isinstance(env_block, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in env_block.items():
        key = str(k or "").strip()
        if not key:
            continue
        if v is None:
            continue
        val = str(v)
        if val == "":
            continue
        out[key] = val
    return out


def load_master_config(repo_root: Path) -> dict | None:
    path = resolve_runtime_config_path(repo_root)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def env_int(name: str, default: int) -> int:
    try:
        raw = str(os.environ.get(name) or "").strip()
        return int(raw) if raw else int(default)
    except Exception:
        return int(default)


def env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if raw == "":
        return bool(default)
    if raw in {"0", "false", "no"}:
        return False
    if raw in {"1", "true", "yes"}:
        return True
    return bool(default)


def load_dotenv(repo_root: str | Path) -> None:
    env_path = Path(repo_root) / ".env"
    dotenv_keys: set[str] = set()
    if not env_path.exists():
        # Also check one level up (common when repo is under user namespace).
        parent_env = Path(repo_root).parent / ".env"
        if parent_env.exists():
            env_path = parent_env
        else:
            env_path = None

    if env_path is not None:
        text = env_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if not os.environ.get(key):
                os.environ[key] = value
                dotenv_keys.add(key)

    # Load runtime config (config/runtime.json) and let it override .env (but not OS env).
    repo_root = Path(repo_root).resolve()
    runtime_env = load_runtime_env(repo_root)
    if runtime_env:
        for key, value in runtime_env.items():
            if key in os.environ and key not in dotenv_keys:
                continue
            os.environ[key] = value

    # Compatibility aliases (common in OpenAI-compatible stacks).
    if not os.environ.get("OPENAI_BASE_URL") and os.environ.get("OPENAI_API_BASE"):
        os.environ["OPENAI_BASE_URL"] = str(os.environ.get("OPENAI_API_BASE") or "")


def normalize_openai_base_url(raw: str) -> str:
    v = str(raw or "").strip()
    if not v:
        return ""
    v = v.rstrip("/")
    if not v.lower().endswith("/v1"):
        v += "/v1"
    return v


def normalize_ollama_base_url(raw: str) -> str:
    v = str(raw or "").strip()
    if not v:
        return ""
    return v.rstrip("/")


def resolve_llm_provider_name(raw: str | None) -> str:
    v = str(raw or "").strip().lower()
    if v in {"openai", "ollama"}:
        return v
    return "openai"
