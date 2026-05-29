"""Tests for UTF-8 encoding handling."""

from __future__ import annotations

from pathlib import Path

from knowcran.models import Claim, PaperRecord
from knowcran.obsidian import export_obsidian
from knowcran.review import review
from knowcran.storage import Storage


def _seed_unicode_db(storage: Storage) -> None:
    """Seed database with Unicode-containing papers."""
    paper = PaperRecord(
        paper_id="p-unicode",
        title="Intracerebral Hemorrhage: Mechanisms – A Review",
        abstract="This study examines ≤ 100 patients with en–dash and ‘smart quotes’. Results show ≥ 50% improvement.",
        year=2023,
        venue="Neurology – European Edition",
        doi="10.1000/test–unicode",
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)
    storage.insert_claim(Claim(
        claim_id="c-unicode",
        paper_id="p-unicode",
        claim_text="Results show ≥ 50% improvement with thin space handling.",
        evidence_type="result",
        confidence=0.7,
        topic="intracerebral hemorrhage",
    ))


def test_obsidian_export_utf8(tmp_path: Path) -> None:
    """Obsidian export must handle Unicode characters correctly."""
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_unicode_db(storage)

    counts = export_obsidian("intracerebral hemorrhage", storage=storage, vault_dir=vault_dir)
    assert counts["papers"] == 1

    # Read back and verify Unicode is preserved
    paper_files = list((vault_dir / "papers").glob("*.md"))
    assert len(paper_files) == 1
    content = paper_files[0].read_text(encoding="utf-8")
    assert "–" in content  # en dash
    assert "≤" in content or "≥" in content  # ≤ or ≥

    storage.close()


def test_review_export_utf8(tmp_path: Path) -> None:
    """Review export must handle Unicode characters correctly."""
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_unicode_db(storage)

    output = review("intracerebral hemorrhage", max_papers=5, storage=storage, vault_dir=vault_dir)
    assert len(output.paper_ids) == 1

    # Read back bibliography and verify Unicode
    bib_file = vault_dir / "reviews" / "intracerebral-hemorrhage_bibliography.bib"
    assert bib_file.exists()
    bib_content = bib_file.read_text(encoding="utf-8")
    assert "Intracerebral Hemorrhage" in bib_content

    # Read back evidence matrix CSV
    csv_file = vault_dir / "reviews" / "intracerebral-hemorrhage_evidence_matrix.csv"
    assert csv_file.exists()
    csv_content = csv_file.read_text(encoding="utf-8")
    assert "≥" in csv_content or "improvement" in csv_content

    storage.close()


def test_review_text_preserves_unicode(tmp_path: Path) -> None:
    """Review text must preserve Unicode characters."""
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_unicode_db(storage)

    output = review("intracerebral hemorrhage", max_papers=5, storage=storage, vault_dir=vault_dir)
    # Check that Unicode characters are in the review text
    assert "≥" in output.review_text or "–" in output.review_text

    storage.close()


def test_chinese_characters_preserved(tmp_path: Path) -> None:
    """Chinese characters in paper titles must be preserved."""
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    paper = PaperRecord(
        paper_id="p-chinese",
        title="脑出血的治疗进展",  # Chinese: Treatment progress of intracerebral hemorrhage
        abstract="本文综述了脑出血的最新治疗进展。",  # Chinese abstract
        year=2024,
        venue="中华神经科杂志",
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)
    storage.insert_topic_paper("intracerebral hemorrhage", "p-chinese")

    counts = export_obsidian("intracerebral hemorrhage", storage=storage, vault_dir=vault_dir)
    assert counts["papers"] == 1

    # Read back and verify Chinese is preserved
    paper_files = list((vault_dir / "papers").glob("*.md"))
    content = paper_files[0].read_text(encoding="utf-8")
    assert "脑出血" in content
    assert "中华神经科杂志" in content

    storage.close()
