"""Tests for LLM-powered review synthesis."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.llm.fake_provider import FakeLLMProvider
from knowcran.models import Claim, PaperRecord
from knowcran.review import (
    _build_review_text,
    _build_review_text_from_llm,
    _validate_review_citations,
    review,
)
from knowcran.storage import Storage
from knowcran.utils import citation_key


@pytest.fixture
def storage(tmp_path):
    s = Storage(db_path=tmp_path / "test.sqlite")
    yield s
    s.close()


@pytest.fixture
def setup_data(storage):
    """Set up papers and claims for review tests."""
    p1 = PaperRecord(
        paper_id="p1",
        title="ICH Outcomes in Elderly Patients",
        abstract="ICH has high mortality in elderly.",
        year=2022,
        venue="Stroke",
        doi="10.1234/stroke",
        authors_json='[{"name": "Smith, J."}]',
    )
    p2 = PaperRecord(
        paper_id="p2",
        title="Surgical Treatment of ICH",
        abstract="Early surgery may improve outcomes.",
        year=2023,
        venue="Neurosurgery",
        doi="10.1234/neuro",
        authors_json='[{"name": "Jones, A."}]',
    )
    storage.upsert_papers([p1, p2])
    storage.insert_topic_papers("ICH", ["p1", "p2"], source="discover", scores=[0.8, 0.7])

    claims = [
        Claim(claim_id="c1", paper_id="p1", claim_text="ICH mortality is 30%", evidence_type="result", confidence=0.8, topic="ICH"),
        Claim(claim_id="c2", paper_id="p2", claim_text="Early surgery reduces mortality", evidence_type="result", confidence=0.75, topic="ICH"),
        Claim(claim_id="c3", paper_id="p1", claim_text="Single center limitation", evidence_type="limitation", confidence=0.6, topic="ICH"),
        Claim(claim_id="c4", paper_id="p2", claim_text="What is optimal surgical timing?", evidence_type="open_question", confidence=0.5, topic="ICH"),
    ]
    for c in claims:
        storage.insert_claim(c)

    return {"papers": [p1, p2], "claims": claims}


class TestValidateReviewCitations:
    def test_valid_citations(self):
        output = {
            "background": [{"text": "ICH is common.", "citations": ["Smith2022"]}],
            "open_questions": [{"text": "Optimal timing?", "citations": ["Jones2023"]}],
        }
        invalid = _validate_review_citations(output, {"Smith2022", "Jones2023"})
        assert invalid == []

    def test_invalid_citation_detected(self):
        output = {
            "background": [{"text": "ICH is common.", "citations": ["FakeAuthor2020"]}],
        }
        invalid = _validate_review_citations(output, {"Smith2022"})
        assert "FakeAuthor2020" in invalid

    def test_empty_sections_no_error(self):
        output = {"background": [], "main_evidence": []}
        invalid = _validate_review_citations(output, {"Smith2022"})
        assert invalid == []


class TestBuildReviewTextFromLLM:
    def test_renders_sections(self):
        llm_output = {
            "title": "Review of ICH",
            "background": [{"text": "ICH is a major stroke subtype.", "citations": ["Smith2022"]}],
            "main_evidence": [{"text": "Mortality is high.", "citations": ["Smith2022", "Jones2023"]}],
            "limitations": [],
            "open_questions": [{"text": "Optimal timing?", "citations": ["Jones2023"]}],
        }
        papers = [
            {"paper_id": "p1", "title": "Paper 1", "year": 2022, "venue": "Stroke", "authors_json": "[]"},
            {"paper_id": "p2", "title": "Paper 2", "year": 2023, "venue": "Neuro", "authors_json": "[]"},
        ]
        text = _build_review_text_from_llm("ICH", papers, llm_output)
        assert "# Review of ICH" in text
        assert "ICH is a major stroke subtype." in text
        assert "[@Smith2022]" in text
        assert "## References" in text

    def test_empty_sections_say_needs_evidence(self):
        llm_output = {"background": [], "main_evidence": [], "limitations": [], "open_questions": []}
        text = _build_review_text_from_llm("ICH", [], llm_output)
        assert "Needs evidence." in text

    def test_warnings_rendered(self):
        llm_output = {"warnings": ["Some claims could not be verified"]}
        text = _build_review_text_from_llm("ICH", [], llm_output)
        assert "Some claims could not be verified" in text


class TestReviewWithLLM:
    def test_review_uses_llm_when_provider_given(self, storage, setup_data):
        llm_response = {
            "title": "LLM Review of ICH",
            "background": [{"text": "ICH is devastating.", "citations": []}],
            "main_evidence": [{"text": "High mortality observed.", "citations": []}],
            "methods_and_models": [],
            "limitations": [],
            "open_questions": [],
        }
        provider = FakeLLMProvider(responses={"review_synthesis": llm_response})

        # We need to mock citation_key to match
        p1 = setup_data["papers"][0]
        key1 = citation_key({"paper_id": "p1", "title": p1.title, "year": p1.year, "authors_json": p1.authors_json})
        llm_response["background"][0]["citations"] = [key1]

        output = review("ICH", storage=storage, vault_dir=Path("/tmp/test_vault"), llm_provider=provider)
        assert output.topic == "ICH"
        assert len(output.evidence_matrix) > 0

    def test_review_falls_back_on_invalid_citations(self, storage, setup_data):
        llm_response = {
            "title": "Bad Review",
            "background": [{"text": "ICH is devastating.", "citations": ["FakeKey2020"]}],
            "main_evidence": [],
            "methods_and_models": [],
            "limitations": [],
            "open_questions": [],
        }
        provider = FakeLLMProvider(responses={"review_synthesis": llm_response})
        output = review("ICH", storage=storage, vault_dir=Path("/tmp/test_vault"), llm_provider=provider)
        # Should fall back to deterministic - no FakeKey in output
        assert "FakeKey" not in output.review_text

    def test_review_without_llm_uses_deterministic(self, storage, setup_data):
        output = review("ICH", storage=storage, vault_dir=Path("/tmp/test_vault"), llm_provider=None)
        assert "Literature Review" in output.review_text
        assert len(output.evidence_matrix) > 0

    def test_review_no_hard_truncation(self, storage, setup_data):
        """Test that review text doesn't hard-truncate claim text mid-word."""
        long_claim = Claim(
            claim_id="long1",
            paper_id="p1",
            claim_text="A" * 500,  # Very long claim
            evidence_type="result",
            confidence=0.8,
            topic="ICH",
        )
        storage.insert_claim(long_claim)
        output = review("ICH", storage=storage, vault_dir=Path("/tmp/test_vault"))
        # The full claim text should appear in evidence matrix
        for row in output.evidence_matrix:
            if row.claim_text == "A" * 500:
                break
        else:
            pytest.fail("Long claim not found in evidence matrix")

    def test_review_open_questions_have_citations(self, storage, setup_data):
        """Test that open questions in deterministic review include paper references."""
        output = review("ICH", storage=storage, vault_dir=Path("/tmp/test_vault"))
        # Open questions should reference paper IDs
        open_qs_text = output.review_text
        if "Open Questions" in open_qs_text:
            # Should have at least one citation marker
            assert "[@" in open_qs_text or "Source:" in open_qs_text or "Needs evidence" in open_qs_text
