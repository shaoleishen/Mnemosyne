"""Tests for SQLite storage."""

from __future__ import annotations

from pathlib import Path

from knowcran.models import Claim, PaperLink, PaperRecord
from knowcran.storage import Storage


def _make_paper(pid: str = "p1", title: str = "Test Paper") -> PaperRecord:
    return PaperRecord(
        paper_id=pid,
        title=title,
        abstract="Test abstract",
        year=2023,
        citation_count=10,
        discovered_by="keyword_search",
    )


def test_init_creates_tables(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    assert storage.count_papers() == 0
    storage.close()


def test_upsert_and_get(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    paper = _make_paper()
    storage.upsert_paper(paper)
    assert storage.count_papers() == 1
    result = storage.get_paper("p1")
    assert result is not None
    assert result["title"] == "Test Paper"
    storage.close()


def test_upsert_updates(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper())
    storage.upsert_paper(_make_paper(title="Updated Title"))
    assert storage.count_papers() == 1
    result = storage.get_paper("p1")
    assert result is not None
    assert result["title"] == "Updated Title"
    storage.close()


def test_insert_and_get_links(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper("p1"))
    storage.upsert_paper(_make_paper("p2"))
    link = PaperLink(source_paper_id="p1", target_paper_id="p2", link_type="reference")
    storage.insert_link(link)
    links = storage.get_links("p1", "reference")
    assert len(links) == 1
    assert links[0]["target_paper_id"] == "p2"
    storage.close()


def test_insert_and_get_claims(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper())
    claim = Claim(
        claim_id="c1",
        paper_id="p1",
        claim_text="Test claim",
        evidence_type="result",
        confidence=0.8,
        topic="test topic",
    )
    storage.insert_claim(claim)
    claims = storage.get_claims_for_paper("p1")
    assert len(claims) == 1
    assert claims[0]["claim_text"] == "Test claim"
    storage.close()


def test_insert_claim_preserves_traceability_fields(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper())
    storage.insert_claim(Claim(
        claim_id="c-trace",
        paper_id="p1",
        claim_text="Traceable claim",
        evidence_type="result",
        confidence=0.9,
        topic="test topic",
        citation_key="Smith2023",
        evidence_status="abstract_only",
        source_quote="Traceable source quote",
        source_span_json='{"start": 0, "end": 22}',
    ))
    claims = storage.get_claims_for_paper("p1")

    assert claims[0]["citation_key"] == "Smith2023"
    assert claims[0]["evidence_status"] == "abstract_only"
    assert claims[0]["source_quote"] == "Traceable source quote"
    assert claims[0]["source_span_json"] == '{"start": 0, "end": 22}'
    storage.close()


def test_get_papers_by_topic(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper("p1", "Celiac Disease Review"))
    storage.upsert_paper(_make_paper("p2", "Unrelated Topic"))
    results = storage.get_papers_by_topic("celiac")
    assert len(results) == 1
    storage.close()


def test_count_functions(tmp_db_path: Path) -> None:
    storage = Storage(db_path=tmp_db_path)
    storage.upsert_paper(_make_paper("p1"))
    storage.upsert_paper(_make_paper("p2"))
    storage.insert_claim(Claim(claim_id="c1", paper_id="p1", claim_text="test", evidence_type="result"))
    storage.insert_link(PaperLink(source_paper_id="p1", target_paper_id="p2", link_type="reference"))
    assert storage.count_papers() == 2
    assert storage.count_claims() == 1
    assert storage.count_links() == 1
    storage.close()
