"""Tests for LLM schemas and prompt contracts."""

from __future__ import annotations

import pytest

from knowcran.llm.schemas import (
    ExtractedEvidenceItem,
    PaperExtractionOutput,
    PaperRelevanceDecision,
    PaperRerankOutput,
    ReviewSectionItem,
    ReviewSynthesisOutput,
)


class TestPaperRelevanceDecision:
    def test_valid_decision(self):
        d = PaperRelevanceDecision(
            paper_id="abc123",
            is_relevant=True,
            score=0.85,
            reason="Directly studies ICH outcomes",
            topic_match="direct",
            study_type="clinical_trial",
        )
        assert d.paper_id == "abc123"
        assert d.score == 0.85

    def test_defaults(self):
        d = PaperRelevanceDecision(paper_id="xyz")
        assert d.is_relevant is True
        assert d.score == 0.5
        assert d.topic_match == "partial"
        assert d.study_type == "other"

    def test_invalid_score_rejected(self):
        with pytest.raises(Exception):
            PaperRelevanceDecision(paper_id="x", score=1.5)
        with pytest.raises(Exception):
            PaperRelevanceDecision(paper_id="x", score=-0.1)

    def test_invalid_topic_match_rejected(self):
        with pytest.raises(Exception):
            PaperRelevanceDecision(paper_id="x", topic_match="very_relevant")

    def test_invalid_study_type_rejected(self):
        with pytest.raises(Exception):
            PaperRelevanceDecision(paper_id="x", study_type="blog_post")


class TestPaperRerankOutput:
    def test_valid_rerank_output(self):
        output = PaperRerankOutput(decisions=[
            PaperRelevanceDecision(paper_id="a", is_relevant=True, score=0.9),
            PaperRelevanceDecision(paper_id="b", is_relevant=False, score=0.1),
        ])
        assert len(output.decisions) == 2
        assert output.decisions[0].score > output.decisions[1].score

    def test_empty_decisions(self):
        output = PaperRerankOutput(decisions=[])
        assert len(output.decisions) == 0


class TestExtractedEvidenceItem:
    def test_valid_item(self):
        item = ExtractedEvidenceItem(
            evidence_type="result",
            claim_text="ICH volume was significantly associated with mortality",
            confidence=0.85,
            source_location="abstract",
            source_quote="ICH volume was significantly associated",
            source_span={"start": 100, "end": 140},
        )
        assert item.evidence_type == "result"
        assert item.confidence == 0.85

    def test_defaults(self):
        item = ExtractedEvidenceItem(evidence_type="method", claim_text="Used MRI scanning")
        assert item.source_location == "abstract"
        assert item.source_span == {"start": 0, "end": 0}

    def test_invalid_evidence_type_rejected(self):
        with pytest.raises(Exception):
            ExtractedEvidenceItem(evidence_type="invalid_type", claim_text="test")

    def test_empty_claim_text_rejected(self):
        with pytest.raises(Exception):
            ExtractedEvidenceItem(evidence_type="result", claim_text="")

    def test_malformed_source_span_fixed(self):
        item = ExtractedEvidenceItem(
            evidence_type="result",
            claim_text="test",
            source_span={"start": -1, "end": -5},
        )
        assert item.source_span == {"start": 0, "end": 0}

    def test_missing_span_keys_fixed(self):
        item = ExtractedEvidenceItem(
            evidence_type="result",
            claim_text="test",
            source_span={"foo": 1},
        )
        assert item.source_span == {"start": 0, "end": 0}


class TestPaperExtractionOutput:
    def test_valid_extraction(self):
        output = PaperExtractionOutput(
            paper_id="abc",
            topic="ICH",
            study_type="clinical_trial",
            population="120 patients with ICH",
            methods=["CT scan analysis"],
            results=["Mortality was 30%"],
            limitations=["Single center"],
            open_questions=["Does treatment X improve outcomes?"],
            evidence_items=[
                ExtractedEvidenceItem(
                    evidence_type="result",
                    claim_text="Mortality was 30%",
                    confidence=0.8,
                ),
            ],
        )
        assert output.paper_id == "abc"
        assert len(output.evidence_items) == 1

    def test_defaults(self):
        output = PaperExtractionOutput(paper_id="xyz")
        assert output.study_type == "other"
        assert output.evidence_items == []
        assert output.population is None


class TestReviewSynthesisOutput:
    def test_valid_review(self):
        output = ReviewSynthesisOutput(
            title="Review of ICH",
            background=[ReviewSectionItem(text="ICH is a major cause of stroke.", citations=["Smith2020"])],
            main_evidence=[ReviewSectionItem(text="Early surgery improves outcomes.", citations=["Jones2021"])],
            limitations=[],
            open_questions=[ReviewSectionItem(text="Optimal timing unclear.", citations=["Smith2020"])],
        )
        assert output.title == "Review of ICH"
        assert len(output.background) == 1
        assert output.background[0].citations == ["Smith2020"]

    def test_empty_review(self):
        output = ReviewSynthesisOutput()
        assert output.title == ""
        assert output.background == []
        assert output.warnings == []
