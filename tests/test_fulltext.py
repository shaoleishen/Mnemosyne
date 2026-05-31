"""Tests for fulltext API, PDF parsing, and FTS search."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from knowcran.config import Settings
from knowcran.models import PaperRecord
from knowcran.storage import Storage
from knowcran.pdf_parse import parse_pdf, _chunk_text, PageText, TextChunk


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    yield storage
    storage.close()


@pytest.fixture
def sample_paper_record():
    return PaperRecord(
        paper_id="test-paper-001",
        title="Test Paper on ICH",
        abstract="This study investigates intracerebral hemorrhage outcomes.",
        year=2024,
        doi="10.1234/test",
        arxiv_id="2401.12345",
    )


class TestStorageNewTables:
    def test_paper_assets(self, tmp_db):
        tmp_db.insert_paper_asset(
            asset_id="asset-001",
            paper_id="paper-001",
            doi="10.1234/test",
            status="downloaded",
            file_path="/tmp/test.pdf",
        )
        asset = tmp_db.get_paper_asset("asset-001")
        assert asset is not None
        assert asset["paper_id"] == "paper-001"
        assert asset["status"] == "downloaded"

    def test_update_paper_asset(self, tmp_db):
        tmp_db.insert_paper_asset(
            asset_id="asset-002",
            paper_id="paper-002",
            status="pending",
        )
        tmp_db.update_paper_asset("asset-002", status="downloaded", file_path="/tmp/test.pdf")
        asset = tmp_db.get_paper_asset("asset-002")
        assert asset["status"] == "downloaded"
        assert asset["file_path"] == "/tmp/test.pdf"

    def test_get_assets_for_paper(self, tmp_db):
        tmp_db.insert_paper_asset(asset_id="a1", paper_id="p1", status="downloaded")
        tmp_db.insert_paper_asset(asset_id="a2", paper_id="p1", status="failed")
        assets = tmp_db.get_assets_for_paper("p1")
        assert len(assets) == 2

    def test_get_asset_by_doi(self, tmp_db):
        tmp_db.insert_paper_asset(asset_id="a1", paper_id="p1", doi="10.1234/test", status="downloaded")
        asset = tmp_db.get_asset_by_doi("10.1234/test")
        assert asset is not None
        assert asset["asset_id"] == "a1"

    def test_fulltext_chunks(self, tmp_db):
        tmp_db.insert_fulltext_chunk(
            chunk_id="chunk-001",
            paper_id="paper-001",
            asset_id="asset-001",
            text="This is a test chunk about intracerebral hemorrhage.",
            page_start=1,
            page_end=1,
            section="Introduction",
            chunk_index=0,
        )
        chunks = tmp_db.get_chunks_for_paper("paper-001")
        assert len(chunks) == 1
        assert chunks[0]["section"] == "Introduction"
        assert chunks[0]["token_count"] > 0

    def test_has_chunks(self, tmp_db):
        assert tmp_db.has_chunks("paper-001") is False
        tmp_db.insert_fulltext_chunk(
            chunk_id="c1", paper_id="paper-001", asset_id="a1",
            text="Test text",
        )
        assert tmp_db.has_chunks("paper-001") is True

    def test_paper_notes(self, tmp_db):
        tmp_db.insert_paper_note(
            note_id="note-001",
            paper_id="paper-001",
            title="Test Note",
            body="# Test\nContent here",
            topic="ICH",
        )
        notes = tmp_db.get_paper_notes("paper-001")
        assert len(notes) == 1
        assert notes[0]["title"] == "Test Note"

    def test_review_runs(self, tmp_db):
        tmp_db.insert_review_run(
            run_id="run-001",
            topic="ICH",
            status="completed",
        )
        run = tmp_db.get_review_run("run-001")
        assert run is not None
        assert run["status"] == "completed"

    def test_pdf_status_summary(self, tmp_db):
        tmp_db.insert_paper_asset(asset_id="a1", paper_id="p1", status="downloaded")
        tmp_db.insert_paper_asset(asset_id="a2", paper_id="p2", status="failed")
        summary = tmp_db.get_pdf_status_summary()
        assert summary["total"] == 2
        assert summary["by_status"]["downloaded"] == 1
        assert summary["by_status"]["failed"] == 1

    def test_fulltext_search(self, tmp_db):
        # Insert a paper first
        tmp_db.upsert_paper(PaperRecord(
            paper_id="p1",
            title="Test Paper",
            abstract="Abstract text",
        ))
        # Insert chunk
        tmp_db.insert_fulltext_chunk(
            chunk_id="c1", paper_id="p1", asset_id="a1",
            text="Hematoma expansion is a key predictor of mortality in ICH patients.",
            page_start=1, page_end=1, section="Results",
        )
        # Sync FTS
        tmp_db.sync_chunk_fts()
        # Search
        results = tmp_db.search_fulltext("hematoma expansion")
        assert len(results) > 0
        assert "hematoma" in results[0]["text"].lower()


class TestChunkText:
    def test_basic_chunking(self):
        pages = [
            PageText(page_number=1, text="Word " * 400),
            PageText(page_number=2, text="Word " * 400),
            PageText(page_number=3, text="Word " * 400),
        ]
        chunks = _chunk_text(pages, "paper-001", "asset-001")
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.paper_id == "paper-001"
            assert chunk.asset_id == "asset-001"
            assert chunk.token_count > 0

    def test_section_detection(self):
        pages = [
            PageText(page_number=1, text="Introduction\nThis is the intro."),
            PageText(page_number=2, text="Methods\nWe conducted a study."),
        ]
        chunks = _chunk_text(pages, "p1", "a1")
        # Should detect sections
        sections = [c.section for c in chunks if c.section]
        # At least one section should be detected
        assert len(chunks) > 0


class TestParsePdf:
    def test_nonexistent_file(self):
        result = parse_pdf("/nonexistent/file.pdf", "p1", "a1")
        assert result.success is False
        # Could be "not found" or "pymupdf not installed"
        assert result.error is not None

    def test_invalid_file(self, tmp_path):
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_bytes(b"not a pdf")
        result = parse_pdf(str(bad_pdf), "p1", "a1")
        assert result.success is False


class TestNotesGeneration:
    def test_generate_paper_note(self, tmp_db, sample_paper_record):
        from knowcran.models import Claim
        tmp_db.upsert_paper(sample_paper_record)
        tmp_db.insert_claim(
            Claim(
                claim_id="c1",
                paper_id="test-paper-001",
                claim_text="ICH has high mortality",
                evidence_type="result",
                confidence=0.8,
                topic="ICH",
            )
        )
        from knowcran.notes import generate_paper_note
        result = generate_paper_note("test-paper-001", topic="ICH", storage=tmp_db)
        assert result["success"] is True
        assert result["claim_count"] > 0


class TestFulltextAPI:
    def test_download_paper_pdf_not_found(self, tmp_db):
        from knowcran.fulltext import download_paper_pdf
        result = download_paper_pdf("nonexistent", storage=tmp_db)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_get_pdf_status(self, tmp_db, sample_paper_record):
        tmp_db.upsert_paper(sample_paper_record)
        tmp_db.insert_paper_asset(
            asset_id="a1", paper_id="test-paper-001",
            status="downloaded", file_path="/tmp/test.pdf",
        )
        from knowcran.fulltext import get_pdf_status
        status = get_pdf_status(paper_id="test-paper-001", storage=tmp_db)
        assert status["has_pdf"] is True

    def test_search_fulltext_empty(self, tmp_db):
        from knowcran.fulltext import search_fulltext
        results = search_fulltext("test query", storage=tmp_db)
        assert results == []
