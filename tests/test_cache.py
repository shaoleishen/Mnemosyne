"""Tests for cache key stability."""

from __future__ import annotations

from knowcran.utils import cache_key


def test_cache_key_deterministic() -> None:
    k1 = cache_key("GET", "https://api.example.com/search", '{"q":"test"}')
    k2 = cache_key("GET", "https://api.example.com/search", '{"q":"test"}')
    assert k1 == k2


def test_cache_key_different_inputs() -> None:
    k1 = cache_key("GET", "https://api.example.com/search", '{"q":"test"}')
    k2 = cache_key("GET", "https://api.example.com/search", '{"q":"other"}')
    assert k1 != k2


def test_cache_key_different_methods() -> None:
    k1 = cache_key("GET", "https://api.example.com/search", "")
    k2 = cache_key("POST", "https://api.example.com/search", "")
    assert k1 != k2


def test_cache_key_different_urls() -> None:
    k1 = cache_key("GET", "https://api.example.com/a", "")
    k2 = cache_key("GET", "https://api.example.com/b", "")
    assert k1 != k2


def test_cache_key_is_sha256_hex() -> None:
    k = cache_key("GET", "https://example.com", "")
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)
