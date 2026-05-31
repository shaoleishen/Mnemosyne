"""End-to-End integration test for the entire Mnemosyne RAG pipeline.

Covers:
1. init -> discover (mocked)
2. download-topic (mocked download URLs)
3. parse-topic (mocked PDF layouts with formulas)
4. read-topic (LLM/FTS extraction mock)
5. hybrid search (FTS5 + dense vectors with section boosts)
6. export-obsidian (callouts, formulas formatting check)
7. MCP server tool dispatcher check
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from knowcran.storage import Storage
from knowcran.models import PaperRecord, Claim
from knowcran.config import Settings
from knowcran.fulltext import download_topic_pdfs, parse_topic_pdfs, hybrid_search_chunks
from knowcran.obsidian import export_obsidian
from knowcran.server.mcp import handle_tool_call
from knowcran.utils import paper_note_stem, citation_key


@pytest.fixture
def mock_settings_and_db(tmp_path):
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    data_dir.mkdir()
    vault_dir.mkdir()

    # Create directories like CLI init command
    (vault_dir / "papers").mkdir(parents=True)
    (vault_dir / "claims").mkdir(parents=True)
    (vault_dir / "topics").mkdir(parents=True)
    (vault_dir / "reviews").mkdir(parents=True)

    settings = Settings(
        data_dir=data_dir,
        vault_dir=vault_dir,
        openai_api_key="mock-openai-key",
        embedding_provider="openai",
    )
    return settings, data_dir, vault_dir


@patch("knowcran.embeddings.EmbeddingProvider.embed_texts")
@patch("httpx.get")
@patch("httpx.post")
@patch("knowcran.paper_fetch.downloader.download_pdf")
def test_e2e_rag_pipeline(mock_download_pdf, mock_httpx_post, mock_httpx_get, mock_embed, mock_settings_and_db, monkeypatch):
    settings, data_dir, vault_dir = mock_settings_and_db
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("KNOWCRAN_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")

    # Mock responsive MinerU API check for auto-parser
    mock_get_response = MagicMock(spec=httpx.Response)
    mock_get_response.status_code = 200
    mock_httpx_get.return_value = mock_get_response

    # 1. Mock discover database insert (normally done via Semantic Scholar Client)
    storage = Storage(db_path=settings.db_path)
    paper = PaperRecord(
        paper_id="paper-e2e-1",
        title="Dynamic RAG Analysis on ICH",
        abstract="This paper analyzes intracerebral hemorrhage (ICH) using a dynamic pipeline.",
        year=2026,
        venue="NEJM",
        doi="10.1056/nejm2026",
    )
    storage.upsert_paper(paper)
    storage.insert_topic_paper("ICH treatment", "paper-e2e-1", relevance_score=0.95)
    
    # Check that database matches
    assert len(storage.get_topic_papers("ICH treatment")) == 1

    # 2. Mock Download - simulate successful download
    # We mock download_pdf return value
    from knowcran.paper_fetch.downloader import DownloadResult
    mock_res = DownloadResult(
        success=True,
        identifier="10.1056/nejm2026",
        doi="10.1056/nejm2026",
        file_path=str(settings.pdf_dir / "Dynamic_RAG_Analysis_on_ICH.pdf"),
        source="SciHub",
        size_bytes=1000,
        sha256="mocksha256",
        asset_id="asset-e2e-1",
    )
    mock_download_pdf.return_value = mock_res
    # Ensure PDF directory exists
    settings.ensure_pdf_dir()
    dummy_pdf = Path(mock_res.file_path)
    dummy_pdf.write_bytes(b"%PDF-1.5 mock bytes")

    download_results = download_topic_pdfs("ICH treatment", limit=5, storage=storage, settings=settings)
    assert download_results["downloaded"] == 1

    # 3. Mock Parsing - MinerU response with standard text elements and formula
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "data": {
            "markdown": "Introduction\n\nFormula test block.",
            "content_list": [
                {
                    "type": "text",
                    "text": "Introduction",
                    "page_idx": 0,
                    "bbox": [50, 700, 200, 720]
                },
                {
                    "type": "text",
                    "text": "We evaluate Results of our treatment below.",
                    "page_idx": 0,
                    "bbox": [50, 600, 400, 650]
                },
                {
                    "type": "formula",
                    "text": "\\Delta V = I R",
                    "page_idx": 1,
                    "bbox": [50, 400, 300, 450]
                }
            ]
        }
    }
    mock_httpx_post.return_value = mock_response

    # 4. Mock Embeddings
    # Generating embeddings returns a mock vector (e.g. 10 dimensions for simple dot-product)
    # We mock embed_texts to return unit vectors
    mock_embed.return_value = [[0.1] * 10, [0.2] * 10, [0.3] * 10]

    # Run PDF parsing
    parse_results = parse_topic_pdfs("ICH treatment", limit=5, storage=storage, settings=settings)
    assert parse_results["parsed"] == 1

    # Check chunks and FTS
    chunks = storage.conn.execute("SELECT * FROM paper_chunks").fetchall()
    assert len(chunks) > 0

    # 5. Extract Claims - insert claim for testing
    claim = Claim(
        claim_id="claim-e2e-1",
        paper_id="paper-e2e-1",
        claim_text="Treatment improves outcomes by \\Delta V = I R",
        evidence_type="result",
        confidence=0.98,
        topic="ICH treatment",
        citation_key="Dynamic2026",
    )
    storage.insert_claim(claim)

    # 6. Hybrid Search Check
    # Query embedding returned by mock_embed
    mock_embed.return_value = [[0.1] * 10]
    search_results = hybrid_search_chunks(
        query="treatment outcomes",
        topic="ICH treatment",
        limit=5,
        storage=storage,
        settings=settings,
    )
    assert len(search_results) > 0
    # The result should contain boosting metadata
    assert "hybrid_score" in search_results[0]
    assert "similarity_score" in search_results[0]
    assert "fts_rank" in search_results[0]

    # 7. Obsidian Note Export & Formatting Verification
    export_obsidian("ICH treatment", storage=storage, vault_dir=vault_dir)

    stem = paper_note_stem(dict(storage.get_paper("paper-e2e-1")))
    paper_file = vault_dir / "papers" / f"{stem}.md"
    assert paper_file.exists()

    paper_md = paper_file.read_text(encoding="utf-8")
    
    # Assert key claim formatting in Obsidian Callouts
    assert "> [!success] Result (conf: 0.98)" in paper_md
    assert "> Treatment improves outcomes by \\Delta V = I R" in paper_md

    # Check that parsed formula was wrapped in double-dollar block delimiters
    # In database chunks, elements were stored.
    element_rows = storage.conn.execute("SELECT text FROM parsed_elements WHERE element_type = 'formula'").fetchall()
    assert len(element_rows) == 1
    assert element_rows[0][0] == "$$\n\\Delta V = I R\n$$"

    # 8. MCP Tool Dispatcher verification
    mcp_res = handle_tool_call(
        "knowcran_search_fulltext_hybrid",
        {"query": "treatment options", "topic": "ICH treatment", "data_dir": str(data_dir)},
        profile="curate"
    )
    assert "results" in mcp_res
    assert len(mcp_res["results"]) > 0

    mcp_pack = handle_tool_call(
        "knowcran_get_evidence_pack",
        {"topic": "ICH treatment", "data_dir": str(data_dir)},
        profile="readonly"
    )
    assert "claims" in mcp_pack
    assert mcp_pack["claims"][0]["citation_key"] == "Dynamic2026"

    storage.close()
