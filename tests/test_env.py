"""Unit tests for core.env functions."""

import os
from core.env import (
    env_int,
    env_bool,
    normalize_openai_base_url,
    normalize_ollama_base_url,
    resolve_llm_provider_name,
)


class TestEnvInt:
    def test_default_when_unset(self):
        assert env_int("_TEST_NONEXISTENT_VAR_", 42) == 42

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("_TEST_INT_VAR_", "7")
        assert env_int("_TEST_INT_VAR_", 0) == 7

    def test_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("_TEST_INT_VAR_", "not_a_number")
        assert env_int("_TEST_INT_VAR_", 99) == 99


class TestEnvBool:
    def test_default_when_unset(self):
        assert env_bool("_TEST_NONEXISTENT_VAR_", True) is True
        assert env_bool("_TEST_NONEXISTENT_VAR_", False) is False

    def test_true_values(self, monkeypatch):
        for val in ("1", "true", "yes", "TRUE", "Yes"):
            monkeypatch.setenv("_TEST_BOOL_VAR_", val)
            assert env_bool("_TEST_BOOL_VAR_", False) is True

    def test_false_values(self, monkeypatch):
        for val in ("0", "false", "no", "FALSE", "No"):
            monkeypatch.setenv("_TEST_BOOL_VAR_", val)
            assert env_bool("_TEST_BOOL_VAR_", True) is False


class TestNormalizeOpenaiBaseUrl:
    def test_appends_v1(self):
        assert normalize_openai_base_url("http://localhost:8080") == "http://localhost:8080/v1"

    def test_keeps_existing_v1(self):
        assert normalize_openai_base_url("http://localhost:8080/v1") == "http://localhost:8080/v1"

    def test_strips_trailing_slash(self):
        assert normalize_openai_base_url("http://localhost:8080/") == "http://localhost:8080/v1"

    def test_empty(self):
        assert normalize_openai_base_url("") == ""


class TestNormalizeOllamaBaseUrl:
    def test_strips_trailing_slash(self):
        assert normalize_ollama_base_url("http://localhost:11434/") == "http://localhost:11434"

    def test_empty(self):
        assert normalize_ollama_base_url("") == ""


class TestResolveLlmProviderName:
    def test_openai(self):
        assert resolve_llm_provider_name("openai") == "openai"

    def test_ollama(self):
        assert resolve_llm_provider_name("ollama") == "ollama"

    def test_default(self):
        assert resolve_llm_provider_name(None) == "openai"
        assert resolve_llm_provider_name("unknown") == "openai"
