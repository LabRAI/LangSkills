"""Smoke tests: verify all core modules can be imported without errors."""


def test_import_core():
    import core
    assert hasattr(core, "__version__")
    assert hasattr(core, "DOMAIN_CONFIG")


def test_import_config():
    from core.config import extract_url_hostname, canonicalize_source_url
    assert callable(extract_url_hostname)
    assert callable(canonicalize_source_url)


def test_import_env():
    from core.env import env_int, env_bool, resolve_llm_provider_name
    assert callable(env_int)
    assert callable(env_bool)
    assert callable(resolve_llm_provider_name)


def test_import_cli():
    from core.cli import main
    assert callable(main)


def test_import_search():
    from core.search import search_skills, format_brief, format_json
    assert callable(search_skills)
    assert callable(format_brief)
    assert callable(format_json)


def test_import_queue():
    from core.queue import QueueSettings, QueueStore
    assert QueueSettings is not None
    assert QueueStore is not None


def test_import_utils():
    from core.utils.hashing import sha256_hex, slugify
    from core.utils.paths import repo_root
    assert callable(sha256_hex)
    assert callable(slugify)
    assert callable(repo_root)
