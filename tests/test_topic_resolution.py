"""P4 Priority Tests: Topic resolution, subtopic isolation, evidence traceability."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.models import Claim, PaperRecord
from knowcran.server.mcp import handle_tool_call
from knowcran.server.tools import get_all_tools
from knowcran.storage import Storage


@pytest.fixture
def db_with_topics(tmp_path):
    """Create a DB with ICH, ICH surgery, and ICH biomarker topics."""
    db_path = tmp_path / "knowcran.sqlite"
    s = Storage(db_path=db_path)

    # ICH papers
    p1 = PaperRecord(paper_id="p-ich-1", title="ICH Outcomes Study", abstract="ICH has high mortality.", year=2023, venue="Stroke")
    p2 = PaperRecord(paper_id="p-ich-2", title="ICH Treatment Review", abstract="Treatment options for ICH.", year=2022, venue="Neurology")
    s.upsert_paper(p1)
    s.upsert_paper(p2)
    s.insert_topic_paper("ICH", "p-ich-1", relevance_score=0.9)
    s.insert_topic_paper("ICH", "p-ich-2", relevance_score=0.8)

    # ICH surgery papers
    p3 = PaperRecord(paper_id="p-surg-1", title="Surgical Evacuation for ICH", abstract="Surgery improves ICH outcomes.", year=2023, venue="JNS")
    s.upsert_paper(p3)
    s.insert_topic_paper("ICH surgery", "p-surg-1", relevance_score=0.85)

    # ICH biomarker papers
    p4 = PaperRecord(paper_id="p-bio-1", title="GFAP as ICH Biomarker", abstract="GFAP predicts ICH outcome.", year=2023, venue="Biomarkers")
    s.upsert_paper(p4)
    s.insert_topic_paper("ICH biomarker", "p-bio-1", relevance_score=0.8)

    # Claims for ICH
    s.insert_claim(Claim(claim_id="c-ich-1", paper_id="p-ich-1", claim_text="ICH mortality is 30%", evidence_type="result", confidence=0.8, topic="ICH"))
    s.insert_claim(Claim(claim_id="c-ich-2", paper_id="p-ich-2", claim_text="Surgery is an option for ICH", evidence_type="abstract_summary", confidence=0.7, topic="ICH"))

    # Claims for ICH surgery
    s.insert_claim(Claim(claim_id="c-surg-1", paper_id="p-surg-1", claim_text="Surgical evacuation reduces mortality", evidence_type="result", confidence=0.75, topic="ICH surgery"))

    # Claims for ICH biomarker
    s.insert_claim(Claim(claim_id="c-bio-1", paper_id="p-bio-1", claim_text="GFAP levels correlate with ICH volume", evidence_type="result", confidence=0.7, topic="ICH biomarker"))

    # Topic relations
    s.add_topic_relation("ICH", "ICH surgery", "subtopic")
    s.add_topic_relation("ICH", "ICH biomarker", "subtopic")

    s.close()
    return tmp_path


class TestTopicResolutionExact:
    """P0: resolve_topic() must NOT use substring matching."""

    def test_resolve_exact_match(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        assert s.resolve_topic("ICH") == "ICH"
        assert s.resolve_topic("ICH surgery") == "ICH surgery"
        assert s.close() is None

    def test_resolve_alias(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        s.add_topic_alias("intracerebral hemorrhage", "ICH")
        assert s.resolve_topic("intracerebral hemorrhage") == "ICH"
        s.close()

    def test_substring_does_not_resolve_to_parent(self, db_with_topics):
        """ICH surgery must NOT resolve to ICH via substring matching."""
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        # This was the old buggy behavior - must not happen
        assert s.resolve_topic("ICH surgery") != "ICH"
        assert s.resolve_topic("ICH surgery") == "ICH surgery"
        s.close()

    def test_unknown_topic_returns_itself(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        assert s.resolve_topic("nonexistent topic") == "nonexistent topic"
        s.close()


class TestSubtopicIsolation:
    """P0: ICH biomarker and ICH surgery claims must not pollute each other."""

    def test_read_topic_subtopic_claims_isolated(self, db_with_topics):
        """Reading 'ICH surgery' should only return surgery claims, not biomarker or parent."""
        from knowcran.reading import read_topic
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        claims = read_topic("ICH surgery", limit=20, storage=s)
        claim_ids = {c.claim_id for c in claims}
        # Should have surgery claims
        assert "c-surg-1" in claim_ids or any("surg" in c.paper_id for c in claims)
        # Should NOT have biomarker claims
        assert "c-bio-1" not in claim_ids
        # Should NOT have parent ICH claims (unless include_parent=True)
        assert "c-ich-1" not in claim_ids
        s.close()

    def test_read_topic_include_parent(self, db_with_topics):
        """With include_parent=True, ICH surgery should also get ICH claims."""
        from knowcran.reading import read_topic
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        claims = read_topic("ICH surgery", limit=20, storage=s, include_parent=True)
        claim_ids = {c.claim_id for c in claims}
        # Should have both surgery and parent claims
        assert "c-ich-1" in claim_ids or any("ich-1" in c.paper_id for c in claims)
        s.close()

    def test_review_uses_same_effective_topic(self, db_with_topics):
        """Review should use the same effective_topic for papers and claims."""
        from knowcran.review import review
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        vault_dir = db_with_topics / "vault"
        output = review("ICH surgery", max_papers=10, storage=s, vault_dir=vault_dir)
        # Claims in evidence matrix should be for ICH surgery, not ICH
        for row in output.evidence_matrix:
            # Surgery claims should be from surgery papers
            assert row.paper_id == "p-surg-1"
        s.close()


class TestTopicRelations:
    """P0: topic_relations table works correctly."""

    def test_add_and_get_subtopics(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        subtopics = s.get_subtopics("ICH")
        assert "ICH surgery" in subtopics
        assert "ICH biomarker" in subtopics
        s.close()

    def test_get_parent_topics(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        parents = s.get_parent_topics("ICH surgery")
        assert "ICH" in parents
        s.close()

    def test_get_topic_family(self, db_with_topics):
        s = Storage(db_path=db_with_topics / "knowcran.sqlite")
        family = s.get_topic_family("ICH surgery")
        assert family["parents"] == ["ICH"]
        assert "ICH biomarker" in family["siblings"]
        s.close()


class TestEvidenceTraceability:
    """P1: evidence_matrix returns citation_key and source_quote."""

    def test_evidence_matrix_has_citation_key_and_source_quote(self, db_with_topics, monkeypatch):
        """Evidence matrix must include citation_key and source_quote fields."""
        monkeypatch.setenv("KNOWCRAN_DATA_DIR", str(db_with_topics))
        result = handle_tool_call("knowcran_get_evidence_matrix", {
            "topic": "ICH",
            "data_dir": str(db_with_topics),
        })
        matrix = result["evidence_matrix"]
        assert len(matrix) > 0
        for row in matrix:
            assert "citation_key" in row
            assert "source_quote" in row
            assert "evidence_status" in row


class TestFastMCPSchema:
    """P3: FastMCP tool schema has required fields."""

    def test_fastmcp_tool_schema_has_required_topic(self):
        """All topic-based tools must have 'topic' in required fields."""
        tools = get_all_tools()
        topic_tools = [t for t in tools if "topic" in t.get("inputSchema", {}).get("properties", {})]
        # topic is optional for these tools
        optional_topic = {"knowcran_search_papers", "knowcran_stats", "knowcran_read_paper"}
        for tool in topic_tools:
            required = tool["inputSchema"].get("required", [])
            if tool["name"] not in optional_topic:
                assert "topic" in required, f"{tool['name']} should require 'topic'"

    def test_readonly_server_creates_successfully(self):
        """Readonly server should create without errors."""
        from knowcran.server.mcp import _create_readonly_server
        server = _create_readonly_server()
        tools = server._tool_manager.list_tools()
        assert len(tools) == 11  # 10 read + 1 audit

    def test_curate_server_creates_successfully(self):
        """Curate server should create without errors."""
        from knowcran.server.mcp import _create_curate_server
        server = _create_curate_server()
        tools = server._tool_manager.list_tools()
        assert len(tools) == 16  # 10 read + 5 write + 1 audit
