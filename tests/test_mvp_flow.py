"""Mocked end-to-end MVP flow test."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from knowcran.discovery import discover
from knowcran.obsidian import export_obsidian
from knowcran.reading import read_topic
from knowcran.review import review
from knowcran.storage import Storage


def _mock_client(tmp_path: Path) -> MagicMock:
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
            "venue": "Nature Medicine",
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
            "venue": "Gastroenterology",
        },
    ]
    client.get_paper.return_value = {"paperId": "p1", "references": [], "citations": []}
    client.get_recommendations.return_value = []
    client.close.return_value = None
    return client


def test_mvp_flow_discover_read_export_review(tmp_path: Path) -> None:
    """Full MVP flow: discover -> read-topic -> export-obsidian -> review."""
    db_path = tmp_path / "test.sqlite"
    vault_dir = tmp_path / "vault"
    storage = Storage(db_path=db_path)
    client = _mock_client(tmp_path)

    # Step 1: Discover
    papers = discover("celiac disease", limit=10, expand=False, client=client, storage=storage)
    assert len(papers) == 2
    assert storage.count_papers() == 2

    # Step 2: Read topic (extract claims)
    claims = read_topic("celiac disease", limit=10, storage=storage)
    assert len(claims) > 0
    assert storage.count_claims() > 0

    # Step 3: Export Obsidian
    counts = export_obsidian("celiac disease", storage=storage, vault_dir=vault_dir)
    assert counts["papers"] == 2
    assert counts["claims"] > 0

    # Verify paper notes exist
    paper_files = list((vault_dir / "papers").glob("*.md"))
    assert len(paper_files) == 2

    # Verify claim notes exist and link to paper note stems
    claim_files = list((vault_dir / "claims").glob("*.md"))
    assert len(claim_files) > 0
    for cf in claim_files:
        content = cf.read_text()
        # Should link to paper note stem (year_slug), not raw paper_id
        assert "[[" in content

    # Step 4: Review
    output = review("celiac disease", max_papers=10, storage=storage, vault_dir=vault_dir)
    assert len(output.paper_ids) == 2
    assert len(output.evidence_matrix) > 0

    # Verify review files exist
    reviews_dir = vault_dir / "reviews"
    assert (reviews_dir / "celiac-disease_review.md").exists()
    assert (reviews_dir / "celiac-disease_evidence_matrix.csv").exists()
    assert (reviews_dir / "celiac-disease_bibliography.bib").exists()
    assert (reviews_dir / "celiac-disease_open_questions.md").exists()

    # Traceability: every evidence row maps to a DB paper
    for row in output.evidence_matrix:
        assert storage.get_paper(row.paper_id) is not None

    # Verify citation keys in review match bibliography
    review_text = (reviews_dir / "celiac-disease_review.md").read_text()
    bib_text = (reviews_dir / "celiac-disease_bibliography.bib").read_text()
    # Extract citation keys from review text [@key]
    import re
    review_keys = set(re.findall(r"\[@(\w+)\]", review_text))
    bib_keys = set(re.findall(r"@article\{(\w+),", bib_text))
    # Every review citation key should exist in bibliography
    for rk in review_keys:
        assert rk in bib_keys, f"Citation key @{rk} in review but not in bibliography"

    storage.close()
