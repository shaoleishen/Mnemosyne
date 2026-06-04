"""Tests for citation key generation and parsing."""

from __future__ import annotations

import re

from knowcran.utils import citation_key


def test_citation_key_with_hyphenated_author() -> None:
    """Citation keys should handle hyphenated author names."""
    paper = {
        "paper_id": "test-hyphen",
        "title": "Intracerebral Hemorrhage Treatment",
        "authors_json": '[{"name": "El-Sherif N."}]',
        "year": 2023,
    }
    key = citation_key(paper)
    assert "el-sherif" in key.lower() or "el" in key.lower()
    assert "2023" in key


def test_citation_key_no_authors() -> None:
    """Citation keys should work without authors."""
    paper = {
        "paper_id": "test-no-auth",
        "title": "Stroke Management Review",
        "authors_json": "[]",
        "year": 2022,
    }
    key = citation_key(paper)
    assert "2022" in key
    assert "stroke" in key.lower()


def test_citation_key_special_chars() -> None:
    """Citation keys should handle special characters in title."""
    paper = {
        "paper_id": "test-special",
        "title": "ICH: Mechanisms & Treatment – A Review",
        "authors_json": '[{"name": "Smith J."}]',
        "year": 2023,
    }
    key = citation_key(paper)
    # Should not contain special chars
    assert "&" not in key
    assert "–" not in key
    assert ":" not in key


def test_citation_key_regex_matches_hyphens() -> None:
    """The citation key regex used in tests should match hyphens."""
    test_key = "el-sherif2023resource"
    pattern = r"\[@([A-Za-z0-9_:-]+)\]"
    match = re.search(pattern, f"[@{test_key}]")
    assert match is not None
    assert match.group(1) == test_key


def test_citation_key_deterministic() -> None:
    """Same paper should produce same citation key."""
    paper = {
        "paper_id": "test-det",
        "title": "Celiac Disease Mechanisms",
        "authors_json": '[{"name": "Doe A."}]',
        "year": 2022,
    }
    key1 = citation_key(paper)
    key2 = citation_key(paper)
    assert key1 == key2
