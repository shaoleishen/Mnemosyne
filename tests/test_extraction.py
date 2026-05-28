"""Tests for LLM-powered extraction module."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.extraction import extract_paper_claims, extract_paper_claims_with_llm
from knowcran.llm.fake_provider import FakeLLMProvider
from knowcran.reading import _extract_claims
from knowcran.storage import Storage


@pytest.fixture
def storage(tmp_path):
    s = Storage(db_path=tmp_path / "test.sqlite")
    yield s
    s.close()


@pytest.fixture
def sample_paper():
    return {
        "paper_id": "test_paper_1",
        "title": "Intracerebral Hemorrhage: Mechanisms and Outcomes",
        "abstract": "BACKGROUND: Intracerebral hemorrhage (ICH) is a devastating stroke subtype. "
                    "METHODS: We conducted a retrospective cohort study of 120 patients. "
                    "RESULTS: Mortality was 30% at 30 days. Hematoma volume was a strong predictor. "
                    "LIMITATIONS: This was a single-center study with limited follow-up. "
                    "CONCLUSION: Early identification of high-risk patients may improve outcomes.",
    }


@pytest.fixture
def llm_extraction_response():
    return {
        "paper_id": "test_paper_1",
        "topic": "ICH",
        "study_type": "cohort",
        "population": "120 patients with ICH",
        "model_or_system": None,
        "methods": ["Retrospective cohort study of 120 patients"],
        "results": ["Mortality was 30% at 30 days", "Hematoma volume was a strong predictor"],
        "limitations": ["Single-center study", "Limited follow-up"],
        "open_questions": ["Does early intervention improve outcomes?"],
        "full_text_needed": [],
        "evidence_items": [
            {
                "evidence_type": "abstract_summary",
                "claim_text": "ICH is a devastating stroke subtype",
                "confidence": 0.9,
                "source_location": "abstract",
                "source_quote": "ICH is a devastating stroke subtype",
                "source_span": {"start": 0, "end": 40},
            },
            {
                "evidence_type": "method",
                "claim_text": "Retrospective cohort study of 120 patients",
                "confidence": 0.85,
                "source_location": "abstract",
                "source_quote": "retrospective cohort study of 120 patients",
                "source_span": {"start": 80, "end": 125},
            },
            {
                "evidence_type": "result",
                "claim_text": "Mortality was 30% at 30 days. Hematoma volume was a strong predictor.",
                "confidence": 0.8,
                "source_location": "abstract",
                "source_quote": "Mortality was 30% at 30 days",
                "source_span": {"start": 130, "end": 160},
            },
            {
                "evidence_type": "limitation",
                "claim_text": "Single-center study with limited follow-up",
                "confidence": 0.7,
                "source_location": "abstract",
                "source_quote": "single-center study with limited follow-up",
                "source_span": {"start": 200, "end": 240},
            },
        ],
    }


class TestLLMExtraction:
    def test_llm_extraction_returns_claims(self, sample_paper, llm_extraction_response):
        provider = FakeLLMProvider(responses={"extraction": llm_extraction_response})
        claims = extract_paper_claims_with_llm(sample_paper, "ICH", provider)
        assert len(claims) == 4
        assert any(c.evidence_type == "result" for c in claims)

    def test_llm_extraction_preserves_paper_id(self, sample_paper, llm_extraction_response):
        provider = FakeLLMProvider(responses={"extraction": llm_extraction_response})
        claims = extract_paper_claims_with_llm(sample_paper, "ICH", provider)
        for claim in claims:
            assert claim.paper_id == "test_paper_1"

    def test_llm_extraction_sets_topic(self, sample_paper, llm_extraction_response):
        provider = FakeLLMProvider(responses={"extraction": llm_extraction_response})
        claims = extract_paper_claims_with_llm(sample_paper, "ICH", provider)
        for claim in claims:
            assert claim.topic == "ICH"


class TestExtractPaperClaims:
    def test_with_llm_provider(self, sample_paper, llm_extraction_response):
        provider = FakeLLMProvider(responses={"extraction": llm_extraction_response})
        claims, method = extract_paper_claims(sample_paper, "ICH", provider)
        assert method == "claw"
        assert len(claims) > 0

    def test_without_llm_provider(self, sample_paper):
        claims, method = extract_paper_claims(sample_paper, "ICH", provider=None)
        assert method == "deterministic"
        assert len(claims) > 0

    def test_llm_failure_falls_back_to_deterministic(self, sample_paper):
        """When LLM fails, extraction should fall back to deterministic mode."""
        from knowcran.llm.base import LLMProviderError

        class FailingProvider:
            def call(self, prompt, task_type="general"):
                raise LLMProviderError("LLM unavailable")

            def is_available(self):
                return True

        claims, method = extract_paper_claims(sample_paper, "ICH", FailingProvider())
        assert method == "deterministic"
        assert len(claims) > 0


class TestIdempotentExtraction:
    def test_repeated_extraction_no_duplicate_claims(self, sample_paper, llm_extraction_response, storage):
        """Test that running extraction twice doesn't create duplicate claims."""
        provider = FakeLLMProvider(responses={"extraction": llm_extraction_response})

        # First extraction
        claims1, method1 = extract_paper_claims(sample_paper, "ICH", provider)
        for c in claims1:
            storage.upsert_claim_idempotent(c, extraction_method=method1)
        count1 = storage.count_claims()

        # Second extraction (same data)
        claims2, method2 = extract_paper_claims(sample_paper, "ICH", provider)
        for c in claims2:
            storage.upsert_claim_idempotent(c, extraction_method=method2)
        count2 = storage.count_claims()

        assert count1 == count2


class TestDeterministicExtraction:
    def test_structured_abstract_labels_cleaned(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "abstract": "BACKGROUND: ICH is common. METHODS: We studied patients. RESULTS: Mortality was high.",
        }
        claims = _extract_claims(paper, "ICH")
        # Should not have "BACKGROUND:" etc. in claim text
        for c in claims:
            assert "BACKGROUND:" not in c.claim_text
            assert "METHODS:" not in c.claim_text
            assert "RESULTS:" not in c.claim_text

    def test_animal_model_produces_translation_question(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "abstract": "We used a murine model of collagenase-induced ICH in rats. "
                        "The results showed increased inflammation markers.",
        }
        claims = _extract_claims(paper, "ICH")
        open_qs = [c for c in claims if c.evidence_type == "open_question"]
        assert len(open_qs) > 0
        assert any("animal" in q.claim_text.lower() or "model" in q.claim_text.lower()
                    or "translate" in q.claim_text.lower() for q in open_qs)
