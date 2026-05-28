"""Reading workflow: deterministic claim extraction from abstracts."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from knowcran.models import Claim
from knowcran.storage import Storage


def _deterministic_claim_id(paper_id: str, topic: str | None, evidence_type: str, claim_text: str, source_location: str) -> str:
    """Generate a deterministic claim ID from content fields."""
    normalized = " ".join(claim_text.lower().split())
    raw = f"{paper_id}:{topic or ''}:{evidence_type}:{normalized}:{source_location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

_METHOD_TERMS = re.compile(
    r"\b(method|model|cohort|trial|assay|dataset|experiment|sample|analysis|design|randomized|controlled)\b",
    re.IGNORECASE,
)
_STRONG_RESULT_TERMS = re.compile(
    r"\b(significant|demonstrate|found|increased|decreased|show)\b",
    re.IGNORECASE,
)
_SUGGESTIVE_RESULT_TERMS = re.compile(
    r"\b(suggest|indicate|associated|correlate|reveal|observed)\b",
    re.IGNORECASE,
)
_LIMITATION_TERMS = re.compile(
    r"\b(limitation|limitation|weakness|caveat|however|although|small sample|further research|preliminary)\b",
    re.IGNORECASE,
)

# Animal/model terms for biomedical-aware open questions
_ANIMAL_MODEL_TERMS = re.compile(
    r"\b(rat|rats|mouse|mice|murine|collagenase[- ]?induced|middle cerebral artery occlusion|MCAO|animal model|in vivo|in vitro|rodent|rodents)\b",
    re.IGNORECASE,
)

# Structured abstract section labels to strip
_ABSTRACT_LABELS = re.compile(
    r"^(BACKGROUND|OBJECTIVE|METHODS?|RESULTS?|CONCLUSIONS?|INTRODUCTION|DISCUSSION|PURPOSE|AIM|DESIGN|SETTING|PATIENTS?|PARTICIPANTS?|INTERVENTIONS?|MAIN OUTCOME MEASURES?|FINDINGS|SIGNIFICANCE|SUMMARY)\s*[:.\-]?\s*",
    re.IGNORECASE,
)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _clean_abstract_labels(text: str) -> str:
    """Strip structured abstract section labels from text."""
    # Split on sentence boundaries to handle inline labels
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned = []
    for sent in sentences:
        sent = _ABSTRACT_LABELS.sub("", sent.strip())
        if sent:
            cleaned.append(sent)
    return " ".join(cleaned)


def _extract_claims(paper: dict[str, Any], topic: str | None = None) -> list[Claim]:
    abstract = paper.get("abstract") or ""
    paper_id = paper["paper_id"]
    cleaned = _clean_abstract_labels(abstract)
    sentences = _split_sentences(cleaned)

    claims: list[Claim] = []

    # abstract_summary: first 1-2 sentences
    summary_text = " ".join(sentences[:2]) if sentences else abstract[:200]
    if summary_text:
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "abstract_summary", summary_text, "abstract"),
            paper_id=paper_id,
            claim_text=summary_text,
            evidence_type="abstract_summary",
            confidence=0.8,
            source_location="abstract",
            topic=topic,
        ))

    # method
    method_sents = [s for s in sentences if _METHOD_TERMS.search(s)]
    if method_sents:
        method_text = " ".join(method_sents[:3])
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "method", method_text, "abstract"),
            paper_id=paper_id,
            claim_text=method_text,
            evidence_type="method",
            confidence=0.7,
            source_location="abstract",
            topic=topic,
        ))

    # result - differentiated by evidence strength
    strong_sents = [s for s in sentences if _STRONG_RESULT_TERMS.search(s)]
    suggestive_sents = [s for s in sentences if _SUGGESTIVE_RESULT_TERMS.search(s)]
    result_sents = strong_sents + [s for s in suggestive_sents if s not in strong_sents]
    if result_sents:
        has_strong = bool(strong_sents)
        confidence = 0.75 if has_strong else 0.55
        result_text = " ".join(result_sents[:3])
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "result", result_text, "abstract"),
            paper_id=paper_id,
            claim_text=result_text,
            evidence_type="result",
            confidence=confidence,
            source_location="abstract",
            topic=topic,
        ))

    # limitation
    limit_sents = [s for s in sentences if _LIMITATION_TERMS.search(s)]
    if limit_sents:
        limit_text = " ".join(limit_sents[:2])
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "limitation", limit_text, "abstract"),
            paper_id=paper_id,
            claim_text=limit_text,
            evidence_type="limitation",
            confidence=0.6,
            source_location="abstract",
            topic=topic,
        ))
    else:
        placeholder = "Needs full text review for limitations"
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "full_text_needed", placeholder, "abstract"),
            paper_id=paper_id,
            claim_text=placeholder,
            evidence_type="full_text_needed",
            confidence=0.3,
            source_location="abstract",
            topic=topic,
        ))

    # open_question - biomedical-aware
    questions: list[str] = []
    if not method_sents:
        questions.append("What specific methodology was used in this study?")
    if not strong_sents and not suggestive_sents:
        questions.append("What were the key findings and effect sizes?")

    # Check if this is an animal/model study
    is_animal_model = bool(_ANIMAL_MODEL_TERMS.search(cleaned))

    if is_animal_model:
        if not any("population" in s.lower() or "patient" in s.lower() or "subject" in s.lower() for s in sentences):
            questions.append("How well does this animal/model finding translate to human disease?")
    else:
        if not any("population" in s.lower() or "patient" in s.lower() or "subject" in s.lower() for s in sentences):
            questions.append("What population or cohort was studied?")
    if questions:
        question_text = "; ".join(questions)
        claims.append(Claim(
            claim_id=_deterministic_claim_id(paper_id, topic, "open_question", question_text, "abstract"),
            paper_id=paper_id,
            claim_text=question_text,
            evidence_type="open_question",
            confidence=0.5,
            source_location="abstract",
            topic=topic,
        ))

    return claims


def read_paper(paper_id: str, topic: str | None = None, storage: Storage | None = None) -> list[Claim]:
    own = storage is None
    storage = storage or Storage()
    try:
        paper = storage.get_paper(paper_id)
        if not paper:
            return []
        topic = topic or paper.get("title", "")
        claims = _extract_claims(paper, topic)
        storage.insert_claims(claims)
        return claims
    finally:
        if own:
            storage.close()


def read_topic(topic: str, limit: int = 20, storage: Storage | None = None,
               llm_provider: Any | None = None) -> list[Claim]:
    own = storage is None
    storage = storage or Storage()
    try:
        # Use explicit topic membership if available, fall back to text search
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=limit)
        else:
            papers = storage.get_papers_by_topic(topic, limit=limit)
        all_claims: list[Claim] = []
        for p in papers:
            if llm_provider is not None:
                from knowcran.extraction import extract_paper_claims
                claims, extraction_method = extract_paper_claims(p, topic, llm_provider)
            else:
                claims = _extract_claims(p, topic)
                extraction_method = "deterministic"

            # Use idempotent upsert to avoid duplicates
            for claim in claims:
                storage.upsert_claim_idempotent(claim, extraction_method=extraction_method)
            all_claims.extend(claims)
        return all_claims
    finally:
        if own:
            storage.close()
