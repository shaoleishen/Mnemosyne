"""Reading workflow: deterministic claim extraction from abstracts."""

from __future__ import annotations

import re
import uuid
from typing import Any

from knowcran.models import Claim
from knowcran.storage import Storage

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


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _extract_claims(paper: dict[str, Any], topic: str | None = None) -> list[Claim]:
    abstract = paper.get("abstract") or ""
    paper_id = paper["paper_id"]
    sentences = _split_sentences(abstract)

    claims: list[Claim] = []

    # abstract_summary: first 1-2 sentences
    summary_text = " ".join(sentences[:2]) if sentences else abstract[:200]
    if summary_text:
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
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
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
            paper_id=paper_id,
            claim_text=" ".join(method_sents[:3]),
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
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
            paper_id=paper_id,
            claim_text=" ".join(result_sents[:3]),
            evidence_type="result",
            confidence=confidence,
            source_location="abstract",
            topic=topic,
        ))

    # limitation
    limit_sents = [s for s in sentences if _LIMITATION_TERMS.search(s)]
    if limit_sents:
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
            paper_id=paper_id,
            claim_text=" ".join(limit_sents[:2]),
            evidence_type="limitation",
            confidence=0.6,
            source_location="abstract",
            topic=topic,
        ))
    else:
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
            paper_id=paper_id,
            claim_text="Needs full text review for limitations",
            evidence_type="limitation",
            confidence=0.3,
            source_location="abstract",
            topic=topic,
        ))

    # open_question
    questions: list[str] = []
    if not method_sents:
        questions.append("What specific methodology was used in this study?")
    if not strong_sents and not suggestive_sents:
        questions.append("What were the key findings and effect sizes?")
    if not any("population" in s.lower() or "patient" in s.lower() or "subject" in s.lower() for s in sentences):
        questions.append("What population or cohort was studied?")
    if questions:
        claims.append(Claim(
            claim_id=str(uuid.uuid4()),
            paper_id=paper_id,
            claim_text="; ".join(questions),
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


def read_topic(topic: str, limit: int = 20, storage: Storage | None = None) -> list[Claim]:
    own = storage is None
    storage = storage or Storage()
    try:
        papers = storage.get_papers_by_topic(topic, limit=limit)
        all_claims: list[Claim] = []
        for p in papers:
            claims = _extract_claims(p, topic)
            storage.insert_claims(claims)
            all_claims.extend(claims)
        return all_claims
    finally:
        if own:
            storage.close()
