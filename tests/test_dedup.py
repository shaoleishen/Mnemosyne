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


def test_dedup_same_normalized_title_missing_ids() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "x1", "title": "Celiac Disease: A Review!", "externalIds": {}},
        {"paperId": "x2", "title": "Celiac Disease - A Review", "externalIds": {}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 1


def test_dedup_doi_case_normalization() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "a", "title": "Paper A", "externalIds": {"DOI": "10.1000/ABC"}},
        {"paperId": "b", "title": "Paper B", "externalIds": {"DOI": "10.1000/abc"}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 1


def test_dedup_same_pmid_missing_doi() -> None:
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "a", "title": "Paper A", "externalIds": {"PubMed": "12345"}},
        {"paperId": "b", "title": "Paper B", "externalIds": {"PubMed": "12345"}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 1


def test_dedup_alias_overlap_across_fields() -> None:
    """Two papers with different IDs but overlapping DOI are deduplicated."""
    from knowcran.discovery import _deduplicate
    papers = [
        {"paperId": "id-1", "title": "Alpha Study", "externalIds": {"DOI": "10.9999/same"}},
        {"paperId": "id-2", "title": "Beta Study", "externalIds": {"DOI": "10.9999/same"}},
        {"paperId": "id-3", "title": "Gamma Study", "externalIds": {"DOI": "10.9999/other"}},
    ]
    result = _deduplicate(papers)
    assert len(result) == 2
