"""Unit tests for core utility functions."""

from core.utils.hashing import sha256_hex, slugify


class TestSha256Hex:
    def test_deterministic(self):
        assert sha256_hex("hello") == sha256_hex("hello")

    def test_different_inputs(self):
        assert sha256_hex("a") != sha256_hex("b")

    def test_returns_hex_string(self):
        result = sha256_hex("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_string(self):
        result = sha256_hex("")
        assert len(result) == 64


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("foo@bar!baz") == "foo-bar-baz"

    def test_consecutive_separators(self):
        assert slugify("a---b___c") == "a-b-c"

    def test_empty_string(self):
        result = slugify("")
        assert result.startswith("t-")

    def test_max_len(self):
        long_text = "a" * 100
        result = slugify(long_text, max_len=20)
        assert len(result) <= 20
