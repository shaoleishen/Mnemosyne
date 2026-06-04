"""End-to-end integration test with mocked S2 API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from knowcran.discovery import discover
from knowcran.reading import read_topic
from knowcran.review import review
from knowcran.storage import Storage


def _mock_s2_client(tmp_path: Path) -> MagicMock:
    client = MagicMock()
    client.search_bulk.return_value = [
        {
            "paperId": "p1",
            "title": "Celiac Disease Autoimmune Mechanism",
            "abstract": "This study demonstrates significant immune response in celiac patients. We used a cohort study with 500 subjects. Results show increased antibody levels.",
            "year": 2023,
            "externalIds": {"DOI": "10.1000/celiac1"},
            "citationCount": 42,
            "referenceCount": 20,
            "influentialCitationCount": 5,
            "openAccessPdf": {"url": "https://example.com/p1.pdf"},
            "authors": [{"name": "Smith J."}],
        },
        {
            "paperId": "p2",
            "title": "Genetic Basis of Celiac Disease",
            "abstract": "We suggest an association between HLA genes and celiac disease. Preliminary findings indicate further research needed.",
            "year": 2022,
            "externalIds": {"DOI": "10.1000/celiac2"},
            "citationCount": 15,
            "referenceCount": 10,
            "influentialCitationCount": 2,
            "openAccessPdf": None,
            "authors": [{"name": "Doe A."}],
        },
    ]
    client.get_paper.return_value = {
        "paperId": "p1",
        "references": [],
        "citations": [],
    }
    client.get_recommendations.return_value = []
    client.close.return_value = None
    return client


def test_discover_read_review_e2e(tmp_path: Path) -> None:
    """Full pipeline: discover -> read-topic -> review, no network calls."""
    db_path = tmp_path / "test.sqlite"
    vault_dir = tmp_path / "vault"
    storage = Storage(db_path=db_path)
    client = _mock_s2_client(tmp_path)

    # Discover
    papers = discover("celiac disease", limit=10, expand=False, client=client, storage=storage)
    assert len(papers) == 2

    # Read topic
    claims = read_topic("celiac disease", limit=5, storage=storage)
    assert len(claims) > 0

    # Review
    output = review("celiac disease", max_papers=5, storage=storage, vault_dir=vault_dir)
    assert len(output.paper_ids) == 2
    assert len(output.evidence_matrix) > 0

    # Traceability: every cited paper exists in DB
    for pid in output.paper_ids:
        assert storage.get_paper(pid) is not None

    # Every evidence row references a DB paper
    for row in output.evidence_matrix:
        assert storage.get_paper(row.paper_id) is not None

    # Review files exist
    reviews_dir = vault_dir / "reviews"
    assert (reviews_dir / "celiac-disease_review.md").exists()
    assert (reviews_dir / "celiac-disease_evidence_matrix.csv").exists()
    assert (reviews_dir / "celiac-disease_bibliography.bib").exists()
    assert (reviews_dir / "celiac-disease_open_questions.md").exists()

    storage.close()
