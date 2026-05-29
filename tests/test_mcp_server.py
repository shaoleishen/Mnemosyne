"""Tests for MCP server tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.models import Claim, PaperRecord
from knowcran.server.tools import (
    get_all_tools, get_read_tools, get_write_tools, get_audit_tools,
    get_read_only_tools, get_admin_tools, get_admin_profile_tools,
)
from knowcran.server.mcp import handle_tool_call
from knowcran.storage import Storage


@pytest.fixture
def data_dir_with_data(tmp_path, monkeypatch):
    """Create a data directory with knowcran.sqlite containing test data.

    Sets KNOWCRAN_DATA_DIR so the security layer allows access to tmp_path.
    """
    db_path = tmp_path / "knowcran.sqlite"
    s = Storage(db_path=db_path)
    p1 = PaperRecord(
        paper_id="p1",
        title="ICH Outcomes Study",
        abstract="ICH has high mortality.",
        year=2023,
        venue="Stroke",
        authors_json='[{"name": "Smith, J."}]',
    )
    s.upsert_paper(p1)
    s.insert_topic_paper("ICH", "p1", relevance_score=0.8)
    s.insert_claim(Claim(
        claim_id="c1", paper_id="p1",
        claim_text="ICH mortality is 30%",
        evidence_type="result", confidence=0.8, topic="ICH",
    ))
    s.close()
    # Allow the security layer to access tmp_path
    monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(tmp_path))
    return tmp_path


class TestMCPTools:
    def test_read_tools_exist(self):
        tools = get_read_tools()
        assert len(tools) > 0
        names = {t["name"] for t in tools}
        assert "knowcran_search_papers" in names
        assert "knowcran_stats" in names

    def test_write_tools_exist(self):
        tools = get_write_tools()
        assert len(tools) > 0
        names = {t["name"] for t in tools}
        assert "knowcran_discover" in names
        assert "knowcran_review" in names

    def test_audit_tools_exist(self):
        tools = get_audit_tools()
        assert len(tools) > 0
        names = {t["name"] for t in tools}
        assert "knowcran_audit_answer" in names

    def test_all_tools_have_schema(self):
        tools = get_all_tools()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert "annotations" in tool

    def test_read_only_tools_do_not_write(self):
        read_names = {t["name"] for t in get_read_tools()}
        write_names = {t["name"] for t in get_write_tools()}
        # No overlap
        assert read_names & write_names == set()

    def test_read_only_server_excludes_write_tools(self):
        readonly_names = {t["name"] for t in get_read_only_tools()}
        write_names = {t["name"] for t in get_write_tools()}
        # Readonly should not contain write tools
        assert readonly_names & write_names == set()
        # But should contain audit tools
        assert "knowcran_audit_answer" in readonly_names

    def test_tool_annotations_readonly(self):
        for tool in get_read_tools():
            ann = tool["annotations"]
            assert ann.readOnlyHint is True
            assert ann.destructiveHint is False

    def test_tool_annotations_write(self):
        for tool in get_write_tools():
            ann = tool["annotations"]
            assert ann.readOnlyHint is False
        # Only discover is open world
        discover_tool = [t for t in get_write_tools() if t["name"] == "knowcran_discover"][0]
        assert discover_tool["annotations"].openWorldHint is True

    def test_tool_annotations_audit(self):
        for tool in get_audit_tools():
            ann = tool["annotations"]
            assert ann.readOnlyHint is True


class TestMCPToolCalls:
    def test_stats(self, data_dir_with_data):
        result = handle_tool_call("knowcran_stats", {"data_dir": str(data_dir_with_data)})
        assert result["papers"] == 1
        assert result["claims"] == 1

    def test_search_papers(self, data_dir_with_data):
        result = handle_tool_call("knowcran_search_papers", {"query": "ICH", "data_dir": str(data_dir_with_data)})
        assert result["count"] >= 1
        assert "has_more" in result

    def test_search_claims(self, data_dir_with_data):
        result = handle_tool_call("knowcran_search_claims", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert result["count"] == 1
        assert "has_more" in result

    def test_unknown_tool_returns_error(self):
        result = handle_tool_call("unknown_tool", {})
        assert "error" in result

    def test_evidence_matrix(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_evidence_matrix", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert "evidence_matrix" in result
        assert result["claim_count"] == 1
        assert "has_abstract_only_evidence" in result

    def test_bibliography(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_bibliography", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert "bibtex" in result
        assert "@" in result["bibtex"]

    def test_bibliography_json_format(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_bibliography", {"topic": "ICH", "format": "json", "data_dir": str(data_dir_with_data)})
        assert "bibliography" in result
        assert result["paper_count"] == 1

    def test_search_papers_pagination(self, data_dir_with_data):
        result = handle_tool_call("knowcran_search_papers", {"query": "ICH", "limit": 1, "offset": 0, "data_dir": str(data_dir_with_data)})
        assert result["count"] <= 1
        assert "has_more" in result
        assert "next_offset" in result

    def test_search_papers_markdown(self, data_dir_with_data):
        result = handle_tool_call("knowcran_search_papers", {"query": "ICH", "response_format": "markdown", "data_dir": str(data_dir_with_data)})
        assert "markdown" in result

    def test_audit_answer(self, data_dir_with_data):
        result = handle_tool_call("knowcran_audit_answer", {
            "topic": "ICH",
            "answer_text": "ICH mortality is 30% [Smith2023]. ICH always causes death.",
            "data_dir": str(data_dir_with_data),
        })
        assert "overclaim_risks" in result
        assert "recommended_revision" in result

    # Legacy compatibility tests (require curate profile for mnemosyne_* names)
    def test_legacy_stats(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "curate")
        result = handle_tool_call("mnemosyne_stats", {"data_dir": str(data_dir_with_data)})
        assert result["papers"] == 1

    def test_legacy_search_papers(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "curate")
        result = handle_tool_call("mnemosyne_search_papers", {"query": "ICH", "data_dir": str(data_dir_with_data)})
        assert result["count"] >= 1


class TestAdminTools:
    """Tests for admin profile tools."""

    def test_admin_tools_exist(self):
        tools = get_admin_tools()
        names = {t["name"] for t in tools}
        assert "knowcran_repair_metadata" in names
        assert "knowcran_dedupe_claims" in names

    def test_admin_profile_includes_all(self):
        all_names = {t["name"] for t in get_all_tools()}
        admin_names = {t["name"] for t in get_admin_profile_tools()}
        # Admin profile should include all regular tools + admin tools
        assert all_names.issubset(admin_names)
        assert "knowcran_repair_metadata" in admin_names

    def test_admin_blocked_in_readonly(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "readonly")
        result = handle_tool_call("knowcran_repair_metadata", {
            "paper_id": "p1",
            "data_dir": str(data_dir_with_data),
        })
        assert "error" in result
        assert "not allowed" in result["error"]

    def test_admin_works_in_admin_profile(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "admin")
        result = handle_tool_call("knowcran_repair_metadata", {
            "paper_id": "p1",
            "data_dir": str(data_dir_with_data),
        })
        assert "paper_id" in result
        assert result["paper_id"] == "p1"
        assert "missing_fields" in result

    def test_repair_metadata_paper_not_found(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "admin")
        result = handle_tool_call("knowcran_repair_metadata", {
            "paper_id": "nonexistent",
            "data_dir": str(data_dir_with_data),
        })
        assert "error" in result

    def test_dedupe_claims(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "admin")
        result = handle_tool_call("knowcran_dedupe_claims", {
            "topic": "ICH",
            "data_dir": str(data_dir_with_data),
        })
        assert "total_claims" in result
        assert "duplicate_groups" in result
        assert result["total_claims"] >= 1


class TestNewReadTools:
    """Tests for new read-only tools added in production refactoring."""

    def test_get_topic_tree(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_topic_tree", {
            "topic": "ICH",
            "data_dir": str(data_dir_with_data),
        })
        assert result["canonical_topic"] == "ICH"
        assert "aliases" in result
        assert "parents" in result
        assert "children" in result

    def test_validate_citations(self, data_dir_with_data):
        result = handle_tool_call("knowcran_validate_citations", {
            "topic": "ICH",
            "text": "ICH mortality is 30% [Smith2023]. This is unrelated text.",
            "data_dir": str(data_dir_with_data),
        })
        assert "valid_citations" in result
        assert "invalid_citations" in result

    def test_get_runs(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_runs", {
            "data_dir": str(data_dir_with_data),
        })
        assert "runs" in result
        assert "count" in result

    def test_get_run_not_found(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_run", {
            "run_id": "nonexistent",
            "data_dir": str(data_dir_with_data),
        })
        assert "error" in result


class TestLimitSemantics:
    """Tests for limit=0 meaning 'all available'."""

    def test_limit_zero_returns_all_papers(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_topic_papers", {
            "topic": "ICH",
            "limit": 0,
            "data_dir": str(data_dir_with_data),
        })
        assert result["count"] >= 1
        assert result["has_more"] is False

    def test_limit_zero_search_papers(self, data_dir_with_data):
        result = handle_tool_call("knowcran_search_papers", {
            "query": "ICH",
            "limit": 0,
            "data_dir": str(data_dir_with_data),
        })
        assert result["count"] >= 1
        assert result["has_more"] is False

    def test_limit_one_has_more(self, data_dir_with_data):
        # With only 1 paper, limit=1 should show has_more=False
        result = handle_tool_call("knowcran_get_topic_papers", {
            "topic": "ICH",
            "limit": 1,
            "data_dir": str(data_dir_with_data),
        })
        assert result["count"] <= 1


class TestDiscoverSkipped:
    """Tests for discover returning existing results on repeated queries."""

    def test_discover_returns_existing_on_repeat(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "curate")
        # The fixture already has topic papers for "ICH"
        result = handle_tool_call("knowcran_discover", {
            "topic": "ICH",
            "data_dir": str(data_dir_with_data),
        })
        # Should return existing papers, not re-fetch
        assert result.get("skipped") is True
        assert result.get("existing_count", 0) >= 1


class TestEvidenceTraceability:
    """Tests for evidence traceability fields in MCP responses."""

    def test_evidence_matrix_has_citation_key_map(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_evidence_matrix", {
            "topic": "ICH",
            "data_dir": str(data_dir_with_data),
        })
        assert "citation_key_map" in result
        assert isinstance(result["citation_key_map"], dict)

    def test_read_topic_returns_traceability_fields(self, data_dir_with_data, monkeypatch):
        monkeypatch.setenv("KNOWCRAN_MCP_PROFILE", "curate")
        result = handle_tool_call("knowcran_read_topic", {
            "topic": "ICH",
            "data_dir": str(data_dir_with_data),
        })
        assert result["count"] >= 1
        claim = result["claims"][0]
        assert "citation_key" in claim
        assert "evidence_status" in claim
        assert "source_quote" in claim

    def test_bibliography_json_uses_citation_key_helper(self, data_dir_with_data):
        result = handle_tool_call("knowcran_get_bibliography", {
            "topic": "ICH",
            "format": "json",
            "data_dir": str(data_dir_with_data),
        })
        assert result["paper_count"] >= 1
        bib = result["bibliography"][0]
        assert "citation_key" in bib
        assert bib["citation_key"]  # Should not be empty
