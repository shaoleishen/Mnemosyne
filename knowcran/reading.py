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
    r"\b(we (conducted|performed|used|employed|applied|collected|recruited|enrolled|randomized|assigned)|"
    r"study (design|population|protocol|procedure)|"
    r"(prospective|retrospective|randomized|controlled|double-blind|placebo-controlled) (study|trial|cohort)|"
    r"(cohort|trial|assay|experiment|survey|questionnaire) (of|with|including|involving)|"
    r"(sample|dataset|data) (of|from|including|consisting)|"
    r"(patients?|subjects?|participants?) (were|was|are|is) (enrolled|recruited|selected|included|divided|randomized)|"
    r"(intervention|treatment|procedure|protocol) (was|were|is|are) (administered|applied|performed|used))\b",
    re.IGNORECASE,
)
_STRONG_RESULT_TERMS = re.compile(
    r"\b(significantly?|demonstrate[sd]?|found that|show[s]? that|increased|decreased|improved|reduced|"
    r"higher|lower|greater|fewer|better|worse|associated with|correlated with|"
    r"mortality was|survival was|outcome[s]? (was|were|showed|demonstrated)|"
    r"the results? (showed|demonstrated|indicated|revealed|suggested)|"
    r"we found|our (results?|findings?) (showed|demonstrated|indicated|suggested))\b",
    re.IGNORECASE,
)
_SUGGESTIVE_RESULT_TERMS = re.compile(
    r"\b(suggest[sd]?|indicate[sd]?|associate[sd]?|correlate[sd]?|reveal[sd]?|observed|"
    r"appear[sd]? to|tend[sd]? to|may (be|have|play|contribute|represent))\b",
    re.IGNORECASE,
)
_LIMITATION_TERMS = re.compile(
    r"\b(limitation[s]?|weakness[es]?|caveat[s]?|"
    r"(however|although|despite|notwithstanding),?\s+(this|our|the|these)|"
    r"small (sample|cohort|number|study)|"
    r"further (research|studies|investigation|work) (is|are|was|were)? needed|"
    r"preliminary (results?|findings?|data)|"
    r"should be (interpreted|cautiously|viewed) (with|cautiously|carefully)|"
    r"this study (has|have|had) (several|some|a few|a number of) limitations?)\b",
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

    # Generate citation_key from paper metadata
    from knowcran.utils import citation_key as gen_citation_key
    ck = gen_citation_key(paper)

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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote=summary_text[:300],
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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote=method_text[:300],
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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote=result_text[:300],
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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote=limit_text[:300],
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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote="",
        ))

    # open_question - biomedical-aware, paper-specific
    questions: list[str] = []

    # Check if this is an animal/model study
    is_animal_model = bool(_ANIMAL_MODEL_TERMS.search(cleaned))

    # Only add questions if the abstract doesn't already answer them
    has_population = any(w in cleaned.lower() for w in ["population", "patient", "subject", "participant", "cohort", "n="])
    has_methodology = bool(method_sents)
    has_results = bool(strong_sents or suggestive_sents)

    # Generate paper-specific open questions
    if is_animal_model and not has_population:
        questions.append(f"What is the translational relevance of these findings to human {topic or 'disease'}?")
    elif not has_population and not has_methodology:
        questions.append(f"What study population and methodology were used to investigate {topic or 'this question'}?")

    # Ask about generalizability if study seems limited
    if any(w in cleaned.lower() for w in ["single center", "single-centre", "retrospective", "small sample", "pilot"]):
        questions.append(f"Are these findings generalizable to broader {topic or ''} populations?")

    # Ask about long-term outcomes if only short-term mentioned
    if any(w in cleaned.lower() for w in ["30-day", "acute", "short-term", "in-hospital"]) and \
       not any(w in cleaned.lower() for w in ["long-term", "1-year", "follow-up", "chronic"]):
        questions.append("What are the long-term outcomes beyond the acute phase?")

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
            citation_key=ck,
            evidence_status="abstract_only",
            source_quote="",
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
               llm_provider: Any | None = None,
               agent_provider: Any | None = None,
               include_parent: bool = False) -> list[Claim]:
    own = storage is None
    storage = storage or Storage()
    try:
        # effective_topic: default is user input, only alias changes it
        resolved_topic = storage.resolve_topic(topic)
        effective_topic = resolved_topic  # Only differs from topic if explicitly aliased

        if effective_topic != topic:
            from rich.console import Console
            Console().print(f"  [dim]Resolved topic '{topic}' -> '{effective_topic}' (alias)[/dim]")

        # Use explicit topic membership if available, fall back to text search
        if storage.has_topic_papers(effective_topic):
            papers = storage.get_topic_papers(effective_topic, limit=limit)
        elif storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=limit)
        else:
            papers = storage.get_papers_by_topic(topic, limit=limit)

        # Only include parent papers if explicitly requested
        if include_parent:
            parent_topics = storage.get_parent_topics(topic)
            for parent in parent_topics:
                parent_papers = storage.get_topic_papers(parent, limit=limit // 2)
                existing_ids = {p["paper_id"] for p in papers}
                for pp in parent_papers:
                    if pp["paper_id"] not in existing_ids:
                        papers.append(pp)

        all_claims: list[Claim] = []

        # Use BulkExecutor for agent-based extraction (parallel chunked)
        if agent_provider is not None:
            from knowcran.agents.bulk_executor import BulkExecutor, format_workflow_summary
            from knowcran.agents.deterministic_provider import DeterministicProvider
            from knowcran.extraction import _parse_extraction_output

            paper_dicts = [{"paper_id": p["paper_id"], "title": p.get("title", ""), "abstract": p.get("abstract", "")} for p in papers]
            executor = BulkExecutor(
                provider=agent_provider,
                fallback_provider=DeterministicProvider(),
                storage=storage,
            )
            claims_dicts, summary = executor.execute_extraction(topic, paper_dicts, storage)
            console.print(f"  [dim]{format_workflow_summary(summary)}[/dim]")

            # Convert extracted evidence items to Claim objects
            for item in claims_dicts:
                paper_id = item.get("_paper_id", "")
                provider_name = item.get("_provider", "deterministic")
                claim_text = item.get("claim_text", "").strip()
                if not claim_text:
                    continue
                evidence_type = item.get("evidence_type", "abstract_summary")
                claim_id = _deterministic_claim_id(paper_id, topic, evidence_type, claim_text, item.get("source_location", "abstract"))
                claim = Claim(
                    claim_id=claim_id,
                    paper_id=paper_id,
                    claim_text=claim_text,
                    evidence_type=evidence_type,
                    confidence=item.get("confidence", 0.5),
                    source_location=item.get("source_location", "abstract"),
                    topic=topic,
                )
                storage.upsert_claim_idempotent(claim, extraction_method=f"agent:{provider_name}")
                all_claims.append(claim)

        elif llm_provider is not None:
            # Legacy LLM provider - extract serially
            from knowcran.extraction import extract_paper_claims
            for p in papers:
                claims, extraction_method = extract_paper_claims(p, topic, provider=llm_provider)
                for claim in claims:
                    storage.upsert_claim_idempotent(claim, extraction_method=extraction_method)
                all_claims.extend(claims)
        else:
            # Deterministic extraction
            for p in papers:
                claims = _extract_claims(p, topic)
                for claim in claims:
                    storage.upsert_claim_idempotent(claim, extraction_method="deterministic")
                all_claims.extend(claims)

        return all_claims
    finally:
        if own:
            storage.close()
