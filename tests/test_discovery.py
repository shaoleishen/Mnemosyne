"""Tests for discovery workflow: candidate selection, deduplication, ranking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from knowcran.discovery import discover
from knowcran.storage import Storage


# Fixture: 5 papers where the best ICH paper is at position 3
_ICH_SEARCH_RESULTS = [
    {
        "paperId": "tangential-1",
        "title": "Direct medical cost of stroke in Singapore",
        "abstract": "We analyze the economic burden of stroke including ischemic stroke and hemorrhagic stroke in Singapore.",
        "year": 2019,
        "externalIds": {"DOI": "10.1000/stroke-cost"},
        "citationCount": 120,
        "referenceCount": 40,
        "influentialCitationCount": 10,
        "openAccessPdf": None,
        "authors": [{"name": "Tan W."}],
        "venue": "Stroke",
    },
    {
        "paperId": "tangential-2",
        "title": "Acute myeloid leukaemia induced by mitoxantrone: case report",
        "abstract": "We report a case of acute myeloid leukaemia following mitoxantrone treatment for multiple sclerosis.",
        "year": 2015,
        "externalIds": {"DOI": "10.1000/leukemia-case"},
        "citationCount": 80,
        "referenceCount": 20,
        "influentialCitationCount": 3,
        "openAccessPdf": None,
        "authors": [{"name": "Johnson R."}],
        "venue": "Leukemia Research",
    },
    {
        "paperId": "best-ich",
        "title": "Hematoma Expansion following Intracerebral Hemorrhage: Mechanisms Targeting the Coagulation Cascade and Platelet Activation",
        "abstract": "Intracerebral hemorrhage (ICH) is a devastating subtype of stroke. Hematoma expansion is a key determinant of neurological deterioration. This review examines mechanisms targeting the coagulation cascade and platelet activation in ICH.",
        "year": 2023,
        "externalIds": {"DOI": "10.1000/ich-hematoma"},
        "citationCount": 45,
        "referenceCount": 60,
        "influentialCitationCount": 8,
        "openAccessPdf": {"url": "https://example.com/ich.pdf"},
        "authors": [{"name": "Zhang Y."}],
        "venue": "Stroke",
    },
    {
        "paperId": "old-ich",
        "title": "Intracerebral hemorrhage and oral amphetamine.",
        "abstract": "A case report of intracerebral hemorrhage associated with oral amphetamine use.",
        "year": 1983,
        "externalIds": {"DOI": "10.1000/amphetamine-ich"},
        "citationCount": 30,
        "referenceCount": 10,
        "influentialCitationCount": 1,
        "openAccessPdf": None,
        "authors": [{"name": "Harrington M."}],
        "venue": "Archives of Neurology",
    },
    {
        "paperId": "developing-topics",
        "title": "Developing Topics.",
        "abstract": "Conference abstract for developing topics session.",
        "year": 2022,
        "externalIds": {"DOI": "10.1000/conf-abstract"},
        "citationCount": 5,
        "referenceCount": 2,
        "influentialCitationCount": 0,
        "openAccessPdf": None,
        "authors": [],
        "venue": "Neurology",
    },
]


def test_best_candidate_beyond_first_two(tmp_path: Path) -> None:
    """The best ICH paper (position 3 in raw results) must be retained after discovery."""
    db_path = tmp_path / "test.sqlite"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    storage = Storage(db_path=db_path)

    client = MagicMock()
    # Return all 5 papers for every query - best is at index 2
    client.search_bulk.return_value = _ICH_SEARCH_RESULTS
    client.close.return_value = None

    papers = discover("intracerebral hemorrhage", limit=3, client=client, storage=storage)

    paper_ids = [p.paper_id for p in papers]
    assert "best-ich" in paper_ids, "Best ICH paper (position 3 in raw) must be retained"

    storage.close()


def test_limit_is_total_not_per_query(tmp_path: Path) -> None:
    """discover(limit=10) must return at most 10 papers total, not 10 per query."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    client = MagicMock()
    # Return 5 papers per query, 5 queries = 25 raw, but limit=10
    client.search_bulk.return_value = _ICH_SEARCH_RESULTS
    client.close.return_value = None

    papers = discover("intracerebral hemorrhage", limit=10, client=client, storage=storage)

    assert len(papers) <= 10, f"Expected at most 10 papers, got {len(papers)}"

    storage.close()


def test_tangential_high_citation_demoted(tmp_path: Path) -> None:
    """A tangential high-citation paper should rank below a strong ICH paper."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    client = MagicMock()
    client.search_bulk.return_value = _ICH_SEARCH_RESULTS
    client.close.return_value = None

    papers = discover("intracerebral hemorrhage", limit=5, client=client, storage=storage)

    # The best ICH paper should rank higher than the tangential leukemia paper
    paper_ids = [p.paper_id for p in papers]
    best_idx = paper_ids.index("best-ich")
    tangential_idx = paper_ids.index("tangential-2")

    assert best_idx < tangential_idx, (
        f"Best ICH paper (index {best_idx}) should rank above tangential leukemia paper (index {tangential_idx})"
    )

    storage.close()


def test_dedup_removes_duplicates(tmp_path: Path) -> None:
    """Duplicate papers across queries must be deduplicated."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    client = MagicMock()
    # Return the same papers for every query - should dedup
    client.search_bulk.return_value = _ICH_SEARCH_RESULTS[:3]
    client.close.return_value = None

    papers = discover("intracerebral hemorrhage", limit=10, client=client, storage=storage)

    # Should have exactly 3 unique papers despite 5 queries
    assert len(papers) == 3, f"Expected 3 unique papers, got {len(papers)}"

    storage.close()
