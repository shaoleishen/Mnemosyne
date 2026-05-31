"""Integration tests for the full-text pipeline.

Tests the end-to-end flow: create paper -> download -> parse -> extract -> search -> review.
Uses mocked PDF data to avoid network dependencies.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from knowcran.config import Settings
from knowcran.models import PaperRecord
from knowcran.storage import Storage


@pytest.fixture
def integration_settings(tmp_path):
    """Create settings with temporary directories."""
    return Settings(
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
        pdf_dir=tmp_path / "data" / "pdfs",
    )


@pytest.fixture
def integration_storage(integration_settings):
    """Create a temporary database."""
    integration_settings.data_dir.mkdir(parents=True, exist_ok=True)
    integration_settings.vault_dir.mkdir(parents=True, exist_ok=True)
    integration_settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    storage = Storage(db_path=integration_settings.db_path)
    yield storage
    storage.close()


@pytest.fixture
def sample_paper():
    """Sample paper for integration testing."""
    return PaperRecord(
        paper_id="integration-test-001",
        title="Hematoma Expansion in Intracerebral Hemorrhage: A Systematic Review",
        abstract="Background: Hematoma expansion is a major predictor of poor outcome in intracerebral hemorrhage. "
                 "Methods: We conducted a systematic review of studies examining hematoma expansion. "
                 "Results: Hematoma expansion occurred in 30% of patients within 6 hours. "
                 "Limitations: Heterogeneity in definitions and imaging protocols. "
                 "Further research is needed to standardize definitions.",
        year=2024,
        doi="10.1234/integration-test",
        arxiv_id="2401.99999",
        open_access_pdf_json=json.dumps({"url": "https://example.com/paper.pdf"}),
    )


def _create_fake_pdf() -> bytes:
    """Create a minimal valid PDF for testing."""
    # Minimal PDF structure
    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>
endobj
4 0 obj
<< /Length 87 >>
stream
BT
/F1 12 Tf
100 700 Td
(Hematoma expansion is a key predictor of mortality.) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
403
%%EOF"""
    return pdf


class TestFulltextIntegration:
    """End-to-end integration tests for the full-text pipeline."""

    def test_paper_creation_and_retrieval(self, integration_storage, sample_paper):
        """Test creating and retrieving a paper."""
        integration_storage.upsert_paper(sample_paper)
        retrieved = integration_storage.get_paper("integration-test-001")
        assert retrieved is not None
        assert retrieved["title"] == sample_paper.title
        assert retrieved["doi"] == "10.1234/integration-test"

    def test_topic_paper_association(self, integration_storage, sample_paper):
        """Test associating papers with topics."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_topic_paper(
            topic="intracerebral hemorrhage",
            paper_id="integration-test-001",
            source="test",
            relevance_score=0.9,
        )
        papers = integration_storage.get_topic_papers("intracerebral hemorrhage")
        assert len(papers) == 1
        assert papers[0]["paper_id"] == "integration-test-001"

    def test_asset_tracking(self, integration_storage, sample_paper):
        """Test PDF asset tracking."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_paper_asset(
            asset_id="test-asset-001",
            paper_id="integration-test-001",
            doi="10.1234/integration-test",
            status="downloaded",
            file_path="/tmp/test.pdf",
            source="test",
        )
        assets = integration_storage.get_assets_for_paper("integration-test-001")
        assert len(assets) == 1
        assert assets[0]["status"] == "downloaded"

    def test_chunk_storage_and_search(self, integration_storage, sample_paper):
        """Test chunk storage and FTS search."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_paper_asset(
            asset_id="test-asset-001",
            paper_id="integration-test-001",
            status="downloaded",
        )
        integration_storage.insert_fulltext_chunk(
            chunk_id="test-chunk-001",
            paper_id="integration-test-001",
            asset_id="test-asset-001",
            text="Hematoma expansion is a major predictor of poor outcome in intracerebral hemorrhage patients.",
            page_start=1,
            page_end=1,
            section="Results",
            chunk_index=0,
        )
        integration_storage.sync_chunk_fts()

        # Test FTS search
        results = integration_storage.search_fulltext("hematoma expansion")
        assert len(results) > 0
        assert "hematoma" in results[0]["text"].lower()

    def test_fts_idempotency(self, integration_storage, sample_paper):
        """Test that FTS rebuild is idempotent."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_paper_asset(
            asset_id="test-asset-001",
            paper_id="integration-test-001",
            status="downloaded",
        )
        integration_storage.insert_fulltext_chunk(
            chunk_id="test-chunk-001",
            paper_id="integration-test-001",
            asset_id="test-asset-001",
            text="Hematoma expansion is a major predictor.",
            page_start=1,
            page_end=1,
            section="Results",
        )

        # Sync multiple times
        integration_storage.sync_chunk_fts()
        integration_storage.sync_chunk_fts()
        integration_storage.sync_chunk_fts()

        # Results should be stable
        results = integration_storage.search_fulltext("hematoma")
        assert len(results) == 1  # Should not duplicate

    def test_abstract_extraction(self, integration_storage, sample_paper):
        """Test abstract claim extraction."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_topic_paper(
            topic="intracerebral hemorrhage",
            paper_id="integration-test-001",
        )

        from knowcran.reading import read_paper
        claims = read_paper("integration-test-001", topic="intracerebral hemorrhage",
                           storage=integration_storage)
        assert len(claims) > 0
        # Check that claims have proper evidence status
        for claim in claims:
            assert claim.evidence_status == "abstract_only"

    def test_fulltext_extraction_with_chunks(self, integration_storage, sample_paper):
        """Test full-text claim extraction when chunks exist."""
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_topic_paper(
            topic="intracerebral hemorrhage",
            paper_id="integration-test-001",
        )
        integration_storage.insert_paper_asset(
            asset_id="test-asset-001",
            paper_id="integration-test-001",
            status="downloaded",
        )
        # Use text that matches the result extraction patterns
        integration_storage.insert_fulltext_chunk(
            chunk_id="test-chunk-001",
            paper_id="integration-test-001",
            asset_id="test-asset-001",
            text="The results showed that hematoma expansion significantly increased mortality risk. "
                 "We found that patients with expansion had worse outcomes.",
            page_start=3,
            page_end=3,
            section="Results",
            chunk_index=0,
        )

        from knowcran.reading import read_paper
        claims = read_paper("integration-test-001", topic="intracerebral hemorrhage",
                           storage=integration_storage, fulltext=True)
        assert len(claims) > 0
        # Should have full-text claims
        ft_claims = [c for c in claims if c.evidence_status == "full_text_reviewed"]
        assert len(ft_claims) > 0

    def test_note_generation(self, integration_storage, sample_paper):
        """Test paper note generation."""
        from knowcran.models import Claim
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_claim(
            Claim(
                claim_id="test-claim-001",
                paper_id="integration-test-001",
                claim_text="Hematoma expansion is a major predictor",
                evidence_type="result",
                confidence=0.85,
                topic="intracerebral hemorrhage",
            )
        )

        from knowcran.notes import generate_paper_note
        result = generate_paper_note("integration-test-001",
                                     topic="intracerebral hemorrhage",
                                     storage=integration_storage)
        assert result["success"] is True
        assert result["claim_count"] > 0

    def test_review_generation(self, integration_storage, sample_paper):
        """Test review generation."""
        from knowcran.models import Claim
        integration_storage.upsert_paper(sample_paper)
        integration_storage.insert_topic_paper(
            topic="intracerebral hemorrhage",
            paper_id="integration-test-001",
        )
        integration_storage.insert_claim(
            Claim(
                claim_id="test-claim-002",
                paper_id="integration-test-001",
                claim_text="Hematoma expansion is a major predictor",
                evidence_type="result",
                confidence=0.85,
                topic="intracerebral hemorrhage",
            )
        )

        from knowcran.review import review
        with tempfile.TemporaryDirectory() as tmpdir:
            output = review("intracerebral hemorrhage", max_papers=10,
                           storage=integration_storage, vault_dir=Path(tmpdir))
            assert len(output.evidence_matrix) > 0
            assert len(output.paper_ids) > 0


class TestMCPProfileGating:
    """Test MCP profile tool gating."""

    def test_readonly_tools(self):
        """Readonly profile should only have read tools."""
        from knowcran.server.tools import get_read_only_tools
        tools = get_read_only_tools()
        tool_names = {t["name"] for t in tools}

        # Should have these
        assert "knowcran_search_papers" in tool_names
        assert "knowcran_search_fulltext" in tool_names
        assert "knowcran_get_pdf_status" in tool_names
        assert "knowcran_audit_answer" in tool_names

        # Should NOT have write tools
        assert "knowcran_discover" not in tool_names
        assert "knowcran_download_paper_pdf" not in tool_names
        assert "knowcran_review" not in tool_names

    def test_curate_tools(self):
        """Curate profile should have all tools."""
        from knowcran.server.tools import get_all_tools
        tools = get_all_tools()
        tool_names = {t["name"] for t in tools}

        # Should have both read and write tools
        assert "knowcran_search_papers" in tool_names
        assert "knowcran_discover" in tool_names
        assert "knowcran_download_paper_pdf" in tool_names
        assert "knowcran_review" in tool_names

    def test_readonly_cannot_discover(self):
        """Readonly profile should not allow discover."""
        from knowcran.server.mcp import handle_tool_call
        result = handle_tool_call("knowcran_discover", {"topic": "test"}, profile="readonly")
        assert "error" in result
        assert "not allowed" in result["error"].lower()
