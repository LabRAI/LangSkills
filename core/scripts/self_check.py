from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import DOMAIN_CONFIG, is_url_allowed_by_config, read_license_policy
from ..env import load_dotenv, resolve_llm_provider_name
from ..utils.fs import can_write_dir
from ..utils.urls import OLLAMA_DEFAULT_BASE_URL


def _ok(msg: str) -> None:
    print(f"OK: {msg}")


def _warn(msg: str) -> None:
    print(f"WARN: {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def run_self_check(*, repo_root: str | Path, skip_remote: bool) -> int:
    repo_root = Path(repo_root).resolve()
    load_dotenv(repo_root)

    failures: list[str] = []

    if sys.version_info >= (3, 10):
        _ok(f"Python version {sys.version.split()[0]}")
    else:
        failures.append(f"Python 3.10+ required; current: {sys.version.split()[0]}")

    provider = resolve_llm_provider_name(__import__("os").environ.get("LLM_PROVIDER") or "openai")
    _ok(f"LLM_PROVIDER={provider}")

    env = __import__("os").environ
    if provider == "openai":
        base_url = str(env.get("OPENAI_BASE_URL") or "").strip()
        api_key = str(env.get("OPENAI_API_KEY") or "").strip()
        if not base_url:
            failures.append("Missing OPENAI_BASE_URL (set in .env)")
        else:
            _ok("OPENAI_BASE_URL set")
        if not api_key:
            failures.append("Missing OPENAI_API_KEY (set in .env)")
        else:
            _ok("OPENAI_API_KEY set")
    elif provider == "ollama":
        model = str(env.get("OLLAMA_MODEL") or "").strip()
        base_url = str(env.get("OLLAMA_BASE_URL") or OLLAMA_DEFAULT_BASE_URL).strip()
        if not model:
            failures.append("Missing OLLAMA_MODEL (required when LLM_PROVIDER=ollama)")
        else:
            _ok("OLLAMA_MODEL set")
        _ok(f"OLLAMA_BASE_URL={base_url}")
    # Optional browser automation: used by Baidu/Zhihu/XHS search.
    try:
        from ..sources.playwright_utils import playwright_available

        if playwright_available():
            _ok("Playwright available")
        else:
            _warn("Playwright not installed (Baidu/Zhihu/XHS search disabled)")
    except Exception:
        _warn("Playwright not installed (Baidu/Zhihu/XHS search disabled)")

    captures_dir = repo_root / "captures"
    if can_write_dir(captures_dir):
        _ok(f"Writable: {captures_dir.relative_to(repo_root).as_posix()}")
    else:
        failures.append(f"Not writable: {captures_dir}")

    skills_dir = repo_root / "skills"
    if can_write_dir(skills_dir):
        _ok(f"Writable: {skills_dir.relative_to(repo_root).as_posix()}")
    else:
        failures.append(f"Not writable: {skills_dir}")

    from ..env import resolve_runtime_config_path

    policy = read_license_policy(repo_root)
    cfg_path = resolve_runtime_config_path(repo_root)
    if policy:
        _ok(f"Found license policy in: {cfg_path.relative_to(repo_root).as_posix()}")
    else:
        failures.append(f"Missing or invalid license policy in: {cfg_path}")

    # Crawl scope sanity check (no network): ensure domain seeds are allowed by allow/deny policy.
    bad: list[tuple[str, str]] = []
    for domain, cfg in DOMAIN_CONFIG.items():
        urls = cfg.get("web_urls") if isinstance(cfg.get("web_urls"), list) else []
        for url in urls:
            u = str(url or "").strip()
            if not u:
                continue
            if not is_url_allowed_by_config(config=cfg, source_type="webpage", url=u):
                bad.append((domain, u))
    if bad:
        failures.append(f"Crawl policy blocks configured web seeds ({len(bad)}); fix DOMAIN_CONFIG.crawl.webpage allow/deny.")
        for domain, url in bad[:10]:
            failures.append(f"Blocked seed: domain={domain} url={url}")
        if len(bad) > 10:
            failures.append(f"... and {len(bad) - 10} more")
    else:
        _ok("Domain crawl policy: web seeds are within allow/deny scope")

    if skip_remote:
        _ok("--skip-remote enabled (no network checks)")
    else:
        _warn("Remote checks are minimal; run a small capture to validate connectivity.")

    if failures:
        for m in failures:
            _fail(m)
        return 1

    print("DONE: self-check passed.")
    return 0


def cli_self_check(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills self-check")
    parser.add_argument("--skip-remote", action="store_true")
    ns = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    return run_self_check(repo_root=repo_root, skip_remote=bool(ns.skip_remote))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_self_check())
