"""Tests for Obsidian export."""

from __future__ import annotations

from pathlib import Path

from knowcran.models import Claim, PaperRecord
from knowcran.obsidian import export_obsidian
from knowcran.storage import Storage


def _seed_db(storage: Storage) -> None:
    paper = PaperRecord(
        paper_id="p1",
        title="Celiac Disease: A Review",
        abstract="Celiac disease is an autoimmune disorder.",
        year=2023,
        venue="Nature Medicine",
        doi="10.1000/test",
        citation_count=42,
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)
    storage.insert_claim(Claim(
        claim_id="c1",
        paper_id="p1",
        claim_text="Celiac disease is autoimmune",
        evidence_type="abstract_summary",
        confidence=0.8,
        topic="celiac disease",
    ))
    storage.insert_claim(Claim(
        claim_id="c2",
        paper_id="p1",
        claim_text="Needs full text review for limitations",
        evidence_type="limitation",
        confidence=0.3,
        topic="celiac disease",
    ))


def test_export_creates_files(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_db(storage)

    counts = export_obsidian("celiac disease", storage=storage, vault_dir=vault_dir)
    assert counts["papers"] == 1
    assert counts["claims"] == 2

    papers_dir = vault_dir / "papers"
    claims_dir = vault_dir / "claims"
    topics_dir = vault_dir / "topics"

    paper_files = list(papers_dir.glob("*.md"))
    claim_files = list(claims_dir.glob("*.md"))
    topic_files = list(topics_dir.glob("*.md"))

    assert len(paper_files) == 1
    assert len(claim_files) == 2
    assert len(topic_files) == 1
    storage.close()


def test_paper_note_has_frontmatter(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_db(storage)
    export_obsidian("celiac disease", storage=storage, vault_dir=vault_dir)

    paper_file = list((vault_dir / "papers").glob("*.md"))[0]
    content = paper_file.read_text()
    assert content.startswith("---")
    assert "paper_id:" in content
    assert "title:" in content
    assert "year:" in content
    assert "tags:" in content
    assert "- paper" in content
    assert "- semantic-scholar" in content
    storage.close()


def test_paper_note_has_sections(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_db(storage)
    export_obsidian("celiac disease", storage=storage, vault_dir=vault_dir)

    paper_file = list((vault_dir / "papers").glob("*.md"))[0]
    content = paper_file.read_text()
    assert "## Abstract" in content
    assert "## Key Claims" in content
    assert "## Limitations" in content
    storage.close()
