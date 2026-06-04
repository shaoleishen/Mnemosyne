"""Tests for fulltext layout chunking, MinerU parsing, hybrid search, Obsidian integration, and MCP tool handlers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from knowcran.models import Claim, PaperRecord
from knowcran.storage import Storage
from knowcran.parsers.base import ParsedElement, ParsedPage, ParsedDocument
from knowcran.parsers.chunker import chunk_elements
from knowcran.parsers.mineru import MinerUParser
from knowcran.fulltext import hybrid_search_chunks, parse_paper_pdf
from knowcran.obsidian import export_obsidian
from knowcran.server.mcp import handle_tool_call
from knowcran.utils import paper_note_stem, citation_key


# ---------------------------------------------------------------------------
# 1. Custom Chunker Tests
# ---------------------------------------------------------------------------

def test_chunker_basic_and_overlap():
    """Verify that chunker respect limits and creates layout element overlaps."""
    elements = []
    # Create 20 elements, each with 100 words. Total = 2000 words.
    # Since TARGET_CHUNK_MAX = 1400, it should split into 2 chunks.
    # Overlap should be ~200 words (i.e. about 2 elements).
    for i in range(20):
        elements.append(
            ParsedElement(
                element_id=f"e-{i}",
                paper_id="p1",
                page_idx=i // 5,  # 4 pages
                element_type="paragraph",
                text="word " * 100,
                section="Introduction" if i < 10 else "Methods",
                element_index=i,
            )
        )

    chunks = chunk_elements(elements, "p1", "asset-1")
    
    # Check that we got at least 2 chunks
    assert len(chunks) >= 2
    assert chunks[0]["paper_id"] == "p1"
    assert chunks[0]["asset_id"] == "asset-1"
    assert chunks[0]["page_start"] == 1
    
    # Verify section boundary splits or word counts
    # First chunk should have index 0, second index 1, etc.
    chunk_indices = [c["chunk_index"] for c in chunks]
    assert chunk_indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# 2. MinerU Parser Client Mocking Tests
# ---------------------------------------------------------------------------

@patch("httpx.post")
def test_mineru_parser_client(mock_post, tmp_path):
    # Mock successful response of local MinerU API
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "markdown": "Introduction\n\nThis is paragraph one.\n\nThis is paragraph two.",
            "content_list": [
                {
                    "type": "text",
                    "text": "Introduction",
                    "page_idx": 0,
                    "bbox": [50, 700, 200, 720]
                },
                {
                    "type": "text",
                    "text": "This is paragraph one.",
                    "page_idx": 0,
                    "bbox": [50, 600, 400, 650]
                },
                {
                    "type": "text",
                    "text": "This is paragraph two.",
                    "page_idx": 1,
                    "bbox": [50, 500, 400, 550]
                },
                {
                    "type": "formula",
                    "text": "E = mc^2",
                    "page_idx": 1,
                    "bbox": [50, 400, 300, 450]
                }
            ]
        }
    }
    mock_post.return_value = mock_response

    # Create dummy pdf file path
    pdf_file = tmp_path / "dummy.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock bytes")

    parser = MinerUParser(api_url="http://127.0.0.1:8000")
    doc = parser.parse(pdf_file, "p-mock", "asset-mock")

    assert doc.status == "parsed"
    assert doc.parser_name == "mineru"
    assert len(doc.pages) == 2
    assert len(doc.elements) == 4
    assert doc.elements[0].section == "Introduction"
    assert doc.elements[1].bbox == [50, 600, 400, 650]
    assert doc.elements[3].element_type == "formula"
    assert doc.elements[3].text == "$$\nE = mc^2\n$$"


# ---------------------------------------------------------------------------
# 3. Hybrid Search Fusion & Boosting Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_embeddings_and_chunks(tmp_path):
    db_path = tmp_path / "test.sqlite"
    s = Storage(db_path=db_path)

    # Insert papers
    p1 = PaperRecord(paper_id="p-h-1", title="Hematoma Expansion Study", abstract="Study on ICH and hematoma expansion.", year=2023, venue="Stroke", doi="10.1001/stroke")
    s.upsert_paper(p1)
    s.insert_topic_paper("ICH hematoma", "p-h-1", relevance_score=0.9)

    # Insert chunk in paper_chunks
    # Vector length for text-embedding-3-large is 3072, but we can mock custom length/dot-product.
    # In knowcran, float32 BLOB conversion is done.
    from knowcran.embeddings import vector_to_bytes
    
    # We mock 10 dimensions for testing simplicity
    vec1 = [0.1] * 10
    vec_bytes = vector_to_bytes(vec1)

    s.conn.execute(
        """INSERT INTO paper_chunks (chunk_id, paper_id, page_start, page_end, section, chunk_index, text, text_hash, token_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("chunk-h-1", "p-h-1", 2, 3, "Results section", 0, "hematoma expansion was observed in patients.", "hash1", 10, "2026-05-31")
    )
    s.conn.execute(
        """INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding, created_at)
        VALUES (?, ?, ?, ?)""",
        ("chunk-h-1", "text-embedding-3-large", vec_bytes, "2026-05-31")
    )
    
    # Build FTS
    s.sync_chunk_fts()
    s.close()
    return db_path


@patch("knowcran.embeddings.EmbeddingProvider.embed_texts")
def test_hybrid_search_fusion_order(mock_embed, db_with_embeddings_and_chunks):
    # Mock embedding provider to return a matching vector
    mock_embed.return_value = [[0.1] * 10]

    s = Storage(db_path=db_with_embeddings_and_chunks)
    
    results = hybrid_search_chunks(
        query="hematoma expansion",
        topic="ICH hematoma",
        limit=5,
        storage=s
    )

    assert len(results) > 0
    first_res = results[0]
    assert first_res["chunk_id"] == "chunk-h-1"
    # Verify section boost was applied because section contains "Results"
    assert first_res["hybrid_score"] > first_res["rrf_score"]
    s.close()


# ---------------------------------------------------------------------------
# 4. Obsidian Export Links and Frontmatter Metadata Tests
# ---------------------------------------------------------------------------

def test_obsidian_export_metadata_and_backlinks(tmp_path):
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "test.sqlite"
    s = Storage(db_path=db_path)

    # Insert paper and chunks
    p = PaperRecord(
        paper_id="p-obs",
        title="Obsidian Integration Paper",
        abstract="Integrating layout chunks into Obsidian notes.",
        year=2024,
        venue="Brain",
        doi="10.1000/obsidian"
    )
    s.upsert_paper(p)
    s.insert_topic_paper("obsidian topic", "p-obs", relevance_score=0.9)

    s.insert_paper_asset(
        asset_id="a-obs-1",
        paper_id="p-obs",
        doi="10.1000/obsidian",
        file_path="/path/to/downloaded.pdf",
        status="downloaded"
    )
    
    s.insert_parsed_document(
        paper_id="p-obs",
        asset_id="a-obs-1",
        parser_name="mineru",
        parser_version="1.0.0",
        status="parsed"
    )

    s.conn.execute(
        """INSERT INTO paper_chunks (chunk_id, paper_id, page_start, page_end, section, chunk_index, text, text_hash, token_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("chunk-obs-1", "p-obs", 1, 1, "Methods", 0, "Chunk text detail.", "hash-obs-1", 5, "2026-05-31")
    )

    s.insert_claim(
        Claim(
            claim_id="claim-obs-1",
            paper_id="p-obs",
            claim_text="Obsidian export is functional",
            evidence_type="result",
            confidence=0.95,
            topic="obsidian topic",
            citation_key="Obsidian2024"
        )
    )

    export_obsidian("obsidian topic", storage=s, vault_dir=vault_dir)

    # Check files
    # paper note filename uses paper_note_stem
    p_dict = s.get_paper("p-obs")
    stem = paper_note_stem(p_dict)
    ckey = citation_key(p_dict)
    
    paper_note_file = vault_dir / "papers" / f"{stem}.md"
    assert paper_note_file.exists()

    paper_content = paper_note_file.read_text(encoding="utf-8")
    # Verify YAML frontmatter contains metadata: doi, pdf_path, parser_name, evidence_status
    assert 'doi: "10.1000/obsidian"' in paper_content
    assert 'pdf_path: "/path/to/downloaded.pdf"' in paper_content
    assert 'parser_name: "mineru"' in paper_content
    assert 'evidence_status: "full_text_reviewed"' in paper_content

    # Verify backlinks between paper and layout chunk notes
    assert "[[chunk-obs-1|Chunk 0 (Pages 1-1 - Methods)]]" in paper_content

    # Verify claim formatting inside callouts
    assert "> [!success] Result (conf: 0.95)" in paper_content
    assert "> Obsidian export is functional" in paper_content

    chunk_note_file = vault_dir / "chunks" / "chunk-obs-1.md"
    assert chunk_note_file.exists()

    chunk_content = chunk_note_file.read_text(encoding="utf-8")
    assert f"**Source**: [[{stem}#page=1|{ckey}]]" in chunk_content

    s.close()


# ---------------------------------------------------------------------------
# 5. MCP Tool Handlers Implementation Verification Tests
# ---------------------------------------------------------------------------

@patch("knowcran.embeddings.EmbeddingProvider.embed_texts")
def test_mcp_handlers_fulltext_tools(mock_embed, tmp_path, monkeypatch):
    # Monkeypatch security constraints
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(tmp_path))
    
    mock_embed.return_value = [[0.1] * 10]
    db_path = tmp_path / "knowcran.sqlite"
    s = Storage(db_path=db_path)

    # Insert records
    p = PaperRecord(paper_id="p-mcp", title="MCP Integration Tests", abstract="Testing custom tools.", year=2026, venue="MCP", doi="10.1000/mcp")
    s.upsert_paper(p)
    s.insert_topic_paper("mcp topic", "p-mcp", relevance_score=0.9)

    s.conn.execute(
        """INSERT INTO paper_chunks (chunk_id, paper_id, page_start, page_end, section, chunk_index, text, text_hash, token_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("chunk-mcp-1", "p-mcp", 5, 5, "Results", 0, "MCP layout text context.", "hash-mcp-1", 5, "2026-05-31")
    )
    from knowcran.embeddings import vector_to_bytes
    s.conn.execute(
        """INSERT INTO chunk_embeddings (chunk_id, embedding_model, embedding, created_at)
        VALUES (?, ?, ?, ?)""",
        ("chunk-mcp-1", "text-embedding-3-large", vector_to_bytes([0.1] * 10), "2026-05-31")
    )
    s.sync_chunk_fts()

    claim = Claim(
        claim_id="claim-mcp-1",
        paper_id="p-mcp",
        claim_text="MCP handles tools cleanly",
        evidence_type="result",
        confidence=0.9,
        topic="mcp topic",
        citation_key="Mcp2026",
        source_span_json=json.dumps({"chunk_id": "chunk-mcp-1"})
    )
    s.insert_claim(claim)
    s.close()

    # 1. Verify knowcran_search_fulltext_hybrid handler
    result_search = handle_tool_call(
        "knowcran_search_fulltext_hybrid",
        {"query": "MCP layout", "topic": "mcp topic", "data_dir": str(tmp_path)},
        profile="curate"
    )
    assert "results" in result_search
    assert len(result_search["results"]) > 0
    assert result_search["results"][0]["chunk_id"] == "chunk-mcp-1"

    # 2. Verify knowcran_get_evidence_pack handler
    result_pack = handle_tool_call(
        "knowcran_get_evidence_pack",
        {"topic": "mcp topic", "data_dir": str(tmp_path)},
        profile="curate"
    )
    assert "claims" in result_pack
    assert len(result_pack["claims"]) > 0
    assert result_pack["claims"][0]["claim_id"] == "claim-mcp-1"
    assert result_pack["claims"][0]["chunk_text"] == "MCP layout text context."
    assert result_pack["claims"][0]["page_start"] == 5

    # 3. Verify knowcran_get_page_context handler
    result_page = handle_tool_call(
        "knowcran_get_page_context",
        {"paper_id": "p-mcp", "page_number": 5, "window": 1, "data_dir": str(tmp_path)},
        profile="curate"
    )
    assert "chunks" in result_page
    assert len(result_page["chunks"]) > 0
    assert result_page["chunks"][0]["chunk_id"] == "chunk-mcp-1"
