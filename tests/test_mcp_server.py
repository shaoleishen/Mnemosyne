"""Tests for MCP server tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.models import Claim, PaperRecord
from knowcran.server.tools import get_all_tools, get_read_tools, get_write_tools
from knowcran.server.mcp import handle_tool_call
from knowcran.storage import Storage


@pytest.fixture
def data_dir_with_data(tmp_path):
    """Create a data directory with knowcran.sqlite containing test data."""
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
    return tmp_path


class TestMCPTools:
    def test_read_tools_exist(self):
        tools = get_read_tools()
        assert len(tools) > 0
        names = {t["name"] for t in tools}
        assert "mnemosyne_search_papers" in names
        assert "mnemosyne_stats" in names

    def test_write_tools_exist(self):
        tools = get_write_tools()
        assert len(tools) > 0
        names = {t["name"] for t in tools}
        assert "mnemosyne_discover" in names
        assert "mnemosyne_review" in names

    def test_all_tools_have_schema(self):
        tools = get_all_tools()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_read_only_tools_do_not_write(self):
        read_names = {t["name"] for t in get_read_tools()}
        write_names = {t["name"] for t in get_write_tools()}
        # No overlap
        assert read_names & write_names == set()


class TestMCPToolCalls:
    def test_stats(self, data_dir_with_data):
        result = handle_tool_call("mnemosyne_stats", {"data_dir": str(data_dir_with_data)})
        assert result["papers"] == 1
        assert result["claims"] == 1

    def test_search_papers(self, data_dir_with_data):
        result = handle_tool_call("mnemosyne_search_papers", {"query": "ICH", "data_dir": str(data_dir_with_data)})
        assert result["count"] >= 1

    def test_search_claims(self, data_dir_with_data):
        result = handle_tool_call("mnemosyne_search_claims", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert result["count"] == 1

    def test_unknown_tool_returns_error(self):
        result = handle_tool_call("unknown_tool", {})
        assert "error" in result

    def test_evidence_matrix(self, data_dir_with_data):
        result = handle_tool_call("mnemosyne_get_evidence_matrix", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert "evidence_matrix" in result
        assert result["claim_count"] == 1

    def test_bibliography(self, data_dir_with_data):
        result = handle_tool_call("mnemosyne_get_bibliography", {"topic": "ICH", "data_dir": str(data_dir_with_data)})
        assert "bibtex" in result
        assert "@" in result["bibtex"]
