"""Unit tests for core.config URL processing functions."""

from core.config import extract_url_hostname, canonicalize_source_url


class TestExtractUrlHostname:
    def test_basic_url(self):
        assert extract_url_hostname("https://github.com/foo/bar") == "github.com"

    def test_with_port(self):
        assert extract_url_hostname("http://localhost:8080/path") == "localhost"

    def test_empty(self):
        assert extract_url_hostname("") == ""
        assert extract_url_hostname(None) == ""

    def test_invalid(self):
        assert extract_url_hostname("not a url") == ""


class TestCanonicalizeSourceUrl:
    def test_empty(self):
        assert canonicalize_source_url("") == ""
        assert canonicalize_source_url(None) == ""

    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=twitter&id=1"
        result = canonicalize_source_url(url)
        assert "utm_source" not in result
        assert "id=1" in result

    def test_strips_github_dot_git(self):
        url = "https://github.com/user/repo.git"
        result = canonicalize_source_url(url)
        assert not result.endswith(".git")

    def test_preserves_valid_params(self):
        url = "https://example.com/page?key=value"
        result = canonicalize_source_url(url)
        assert "key=value" in result
