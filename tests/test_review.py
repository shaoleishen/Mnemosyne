"""Tests for review generation and citation traceability."""

from __future__ import annotations

from pathlib import Path

from knowcran.models import Claim, PaperRecord
from knowcran.review import review
from knowcran.storage import Storage


def _seed_review_db(storage: Storage) -> None:
    for i in range(3):
        paper = PaperRecord(
            paper_id=f"p{i}",
            title=f"Paper {i} about Celiac Disease",
            abstract=f"Abstract for paper {i} on celiac disease.",
            year=2020 + i,
            venue="Test Journal",
            doi=f"10.1000/test{i}",
            discovered_by="keyword_search",
        )
        storage.upsert_paper(paper)
        storage.insert_claim(Claim(
            claim_id=f"c{i}-result",
            paper_id=f"p{i}",
            claim_text=f"Result finding from paper {i}",
            evidence_type="result",
            confidence=0.7,
            topic="celiac disease",
        ))
        storage.insert_claim(Claim(
            claim_id=f"c{i}-method",
            paper_id=f"p{i}",
            claim_text=f"Method used in paper {i}",
            evidence_type="method",
            confidence=0.6,
            topic="celiac disease",
        ))


def test_review_generates_files(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_review_db(storage)

    output = review("celiac disease", max_papers=5, storage=storage, vault_dir=vault_dir)
    assert len(output.paper_ids) == 3
    assert len(output.evidence_matrix) == 6

    reviews_dir = vault_dir / "reviews"
    assert (reviews_dir / "celiac-disease_review.md").exists()
    assert (reviews_dir / "celiac-disease_evidence_matrix.csv").exists()
    assert (reviews_dir / "celiac-disease_bibliography.bib").exists()
    assert (reviews_dir / "celiac-disease_open_questions.md").exists()
    storage.close()


def test_review_citations_trace_to_db(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_review_db(storage)

    output = review("celiac disease", max_papers=5, storage=storage, vault_dir=vault_dir)

    # Every cited paper_id must exist in the database
    for pid in output.paper_ids:
        paper = storage.get_paper(pid)
        assert paper is not None, f"Paper {pid} cited in review but not in DB"

    # Every evidence matrix row must reference a DB paper
    for row in output.evidence_matrix:
        paper = storage.get_paper(row.paper_id)
        assert paper is not None, f"Evidence row references {row.paper_id} not in DB"

    storage.close()


def test_review_text_has_sections(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_review_db(storage)

    output = review("celiac disease", max_papers=5, storage=storage, vault_dir=vault_dir)
    text = output.review_text
    assert "# Literature Review: celiac disease" in text
    assert "## Background" in text
    assert "## Main Evidence" in text
    assert "## Methods And Models" in text
    assert "## Limitations" in text
    assert "## Open Questions" in text
    assert "## References" in text
    storage.close()


def test_review_scopes_claims_to_selected_papers(tmp_path: Path) -> None:
    """Regression: max_papers limits papers AND their claims only."""
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_review_db(storage)

    # Only 1 paper selected, so only its 2 claims should appear
    output = review("celiac disease", max_papers=1, storage=storage, vault_dir=vault_dir)
    assert len(output.paper_ids) == 1
    assert len(output.evidence_matrix) == 2
    for row in output.evidence_matrix:
        assert row.paper_id == output.paper_ids[0]
    storage.close()
