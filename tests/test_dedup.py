"""Tests for deduplication logic."""

from __future__ import annotations

from knowcran.utils import normalize_title


def test_normalize_title_removes_punctuation() -> None:
    assert normalize_title("Celiac Disease: A Review!") == "celiac disease a review"


def test_normalize_title_collapses_whitespace() -> None:
    assert normalize_title("  Celiac   Disease  ") == "celiac disease"


def test_dedup_by_paper_id() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "abc", "title": "Paper A", "externalIds": {}},
        {"paperId": "abc", "title": "Paper A Duplicate", "externalIds": {}},
        {"paperId": "def", "title": "Paper B", "externalIds": {}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 2


def test_dedup_by_doi() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "id1", "title": "Paper X", "externalIds": {"DOI": "10.1000/x"}},
        {"paperId": "id2", "title": "Paper X Same DOI", "externalIds": {"DOI": "10.1000/x"}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 1


def test_dedup_by_pmid() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "id1", "title": "Paper Y", "externalIds": {"PubMed": "99999"}},
        {"paperId": "id2", "title": "Paper Y Same PMID", "externalIds": {"PubMed": "99999"}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 1


def test_dedup_distinct_papers() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "a", "title": "First", "externalIds": {}},
        {"paperId": "b", "title": "Second", "externalIds": {}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 2
