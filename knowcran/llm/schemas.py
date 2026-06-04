"""Pydantic schemas for LLM structured outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PaperRelevanceDecision(BaseModel):
    """Single paper relevance decision from LLM reranking."""

    paper_id: str
    is_relevant: bool = True
    score: float = Field(ge=0.0, le=1.0, default=0.5)
    reason: str = ""
    topic_match: Literal["direct", "partial", "tangential", "irrelevant"] = "partial"
    study_type: Literal[
        "review", "clinical_trial", "cohort", "case_report",
        "animal_model", "mechanism", "guideline", "other",
    ] = "other"


class PaperRerankOutput(BaseModel):
    """Output from LLM reranking a batch of papers."""

    decisions: list[PaperRelevanceDecision]


class ExtractedEvidenceItem(BaseModel):
    """A single evidence item extracted from a paper."""

    evidence_type: Literal[
        "abstract_summary", "method", "result", "limitation",
        "open_question", "full_text_needed",
    ]
    claim_text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source_location: str = "abstract"
    source_quote: str = ""
    source_span: dict[str, int] = Field(default_factory=lambda: {"start": 0, "end": 0})

    @field_validator("source_span")
    @classmethod
    def validate_source_span(cls, v: dict[str, int]) -> dict[str, int]:
        if "start" not in v or "end" not in v:
            return {"start": 0, "end": 0}
        if v["start"] < 0 or v["end"] < v["start"]:
            return {"start": 0, "end": 0}
        return v


class PaperExtractionOutput(BaseModel):
    """Output from LLM extraction of a single paper."""

    paper_id: str
    topic: str = ""
    study_type: str = "other"
    population: str | None = None
    model_or_system: str | None = None
    methods: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    full_text_needed: list[str] = Field(default_factory=list)
    evidence_items: list[ExtractedEvidenceItem] = Field(default_factory=list)


class ReviewSectionItem(BaseModel):
    """A single item in a review section (text + citations)."""

    text: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


class ReviewSynthesisOutput(BaseModel):
    """Output from LLM review synthesis."""

    title: str = ""
    background: list[ReviewSectionItem] = Field(default_factory=list)
    main_evidence: list[ReviewSectionItem] = Field(default_factory=list)
    methods_and_models: list[ReviewSectionItem] = Field(default_factory=list)
    limitations: list[ReviewSectionItem] = Field(default_factory=list)
    open_questions: list[ReviewSectionItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
