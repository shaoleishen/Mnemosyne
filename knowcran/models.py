"""Data models for KnowCran."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchQuestion(BaseModel):
    question: str
    limit: int = 100
    expand: bool = False


class PaperRecord(BaseModel):
    paper_id: str
    title: str
    abstract: str | None = None
    year: int | None = None
    publication_date: str | None = None
    venue: str | None = None
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None
    arxiv_id: str | None = None
    citation_count: int = 0
    reference_count: int = 0
    influential_citation_count: int = 0
    fields_json: str | None = None
    authors_json: str | None = None
    external_ids_json: str | None = None
    open_access_pdf_json: str | None = None
    discovered_by: str = "keyword_search"
    relevance_score: float = 0.0
    created_at: str = ""
    updated_at: str = ""

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def default_timestamp(cls, v: str) -> str:
        if not v:
            return datetime.now(timezone.utc).isoformat()
        return v

    @classmethod
    def from_s2(cls, data: dict[str, Any], discovered_by: str = "keyword_search") -> PaperRecord:
        ext = data.get("externalIds") or {}
        return cls(
            paper_id=data["paperId"],
            title=data.get("title", ""),
            abstract=data.get("abstract"),
            year=data.get("year"),
            publication_date=data.get("publicationDate"),
            venue=data.get("venue"),
            url=data.get("url"),
            doi=ext.get("DOI"),
            pmid=ext.get("PubMed"),
            arxiv_id=ext.get("ArXiv"),
            citation_count=data.get("citationCount", 0),
            reference_count=data.get("referenceCount", 0),
            influential_citation_count=data.get("influentialCitationCount", 0),
            fields_json=json.dumps(data.get("fieldsOfStudy")),
            authors_json=json.dumps(data.get("authors")),
            external_ids_json=json.dumps(data.get("externalIds")),
            open_access_pdf_json=json.dumps(data.get("openAccessPdf")),
            discovered_by=discovered_by,
        )


class PaperLink(BaseModel):
    source_paper_id: str
    target_paper_id: str
    link_type: str  # reference, citation, recommendation
    created_at: str = ""


class Claim(BaseModel):
    claim_id: str
    paper_id: str
    claim_text: str
    evidence_type: str  # abstract_summary, method, result, limitation, open_question
    confidence: float = 0.5
    source_location: str = "abstract"
    topic: str | None = None
    created_at: str = ""


class EvidenceMatrixRow(BaseModel):
    paper_id: str
    title: str
    year: int | None
    claim_text: str
    evidence_type: str
    confidence: float


class ReviewRequest(BaseModel):
    topic: str
    max_papers: int = 20


class ReviewOutput(BaseModel):
    topic: str
    review_text: str
    evidence_matrix: list[EvidenceMatrixRow]
    open_questions: list[str]
    paper_ids: list[str]
