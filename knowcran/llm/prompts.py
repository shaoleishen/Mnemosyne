"""Prompt builders for KnowCran LLM tasks."""

from __future__ import annotations

from typing import Any


def build_relevance_prompt(topic: str, papers: list[dict[str, Any]]) -> str:
    """Build a prompt for LLM relevance reranking.

    Args:
        topic: The research topic.
        papers: List of paper dicts with at least paper_id, title, abstract.

    Returns:
        A prompt string demanding strict JSON output.
    """
    paper_entries = []
    for p in papers:
        abstract = (p.get("abstract") or "")[:500]
        entry = f'{{"paper_id": "{p["paper_id"]}", "title": "{p.get("title", "")}", "abstract": "{abstract}"}}'
        paper_entries.append(entry)

    papers_json = ",\n  ".join(paper_entries)

    return f"""You are a biomedical literature relevance assessor.

TASK: For each paper below, decide if it is relevant to the topic "{topic}".

For each paper, output a JSON object with:
- paper_id: the paper ID
- is_relevant: boolean
- score: relevance score from 0.0 to 1.0
- reason: short reason (max 50 words)
- topic_match: one of "direct", "partial", "tangential", "irrelevant"
- study_type: one of "review", "clinical_trial", "cohort", "case_report", "animal_model", "mechanism", "guideline", "other"

Return a JSON object with key "decisions" containing a list of these objects.

PAPERS:
[
  {papers_json}
]

IMPORTANT:
- Return ONLY valid JSON, no markdown fences or explanation.
- Every paper must have a decision.
- Do not invent information not present in the title or abstract."""


def build_extraction_prompt(topic: str, paper: dict[str, Any]) -> str:
    """Build a prompt for LLM claim extraction from a paper.

    Args:
        topic: The research topic.
        paper: Paper dict with paper_id, title, abstract.

    Returns:
        A prompt string demanding strict JSON output.
    """
    abstract = paper.get("abstract") or ""
    paper_id = paper["paper_id"]
    title = paper.get("title", "")

    return f"""You are a biomedical evidence extractor.

TASK: Extract structured evidence from this paper about "{topic}".

PAPER:
- paper_id: {paper_id}
- title: {title}
- abstract: {abstract}

Return a JSON object with these fields:
- paper_id: "{paper_id}"
- topic: "{topic}"
- study_type: one of "review", "clinical_trial", "cohort", "case_report", "animal_model", "mechanism", "guideline", "other"
- population: description of study population or null
- model_or_system: description of model/system used or null
- methods: list of method descriptions
- results: list of key findings
- limitations: list of limitations mentioned in abstract
- open_questions: list of questions NOT answered by this paper alone
- full_text_needed: list of claims that need full text review
- evidence_items: list of objects with:
  - evidence_type: "abstract_summary", "method", "result", "limitation", "open_question", or "full_text_needed"
  - claim_text: the extracted claim
  - confidence: 0.0 to 1.0
  - source_location: "abstract"
  - source_quote: exact short quote from abstract (max 100 chars)
  - source_span: {{"start": 0, "end": 0}} or character offsets if known

IMPORTANT:
- Return ONLY valid JSON, no markdown fences or explanation.
- Do not invent claims not supported by the abstract.
- If information is missing, leave the list empty or use null.
- Limitations not in the abstract should go in full_text_needed."""


def build_review_prompt(topic: str, papers: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    """Build a prompt for LLM review synthesis.

    Args:
        topic: The research topic.
        papers: List of paper dicts with paper_id, title, year, venue.
        claims: List of claim dicts with paper_id, claim_text, evidence_type.

    Returns:
        A prompt string demanding strict JSON output with citation keys.
    """
    from knowcran.utils import citation_key

    # Build paper reference with citation keys
    paper_refs = []
    citation_keys_map: dict[str, str] = {}
    for p in papers:
        key = citation_key(p)
        citation_keys_map[p["paper_id"]] = key
        paper_refs.append(f'  "{key}": paper_id={p["paper_id"]}, title="{p.get("title", "")}", year={p.get("year", "N/A")}')

    papers_section = ",\n".join(paper_refs)

    # Build claims section grouped by evidence type
    claims_by_type: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        claims_by_type.setdefault(c["evidence_type"], []).append(c)

    claims_sections = []
    for etype, group in claims_by_type.items():
        items = []
        for c in group:
            key = citation_keys_map.get(c["paper_id"], c["paper_id"])
            items.append(f'    {{"paper_citation_key": "{key}", "claim_text": "{c["claim_text"]}"}}')
        claims_sections.append(f'  "{etype}": [\n' + ",\n".join(items) + "\n  ]")

    claims_section = ",\n".join(claims_sections)

    all_keys = list(set(citation_keys_map.values()))
    keys_str = ", ".join(f'"{k}"' for k in all_keys)

    return f"""You are a scientific literature reviewer.

TASK: Write a structured literature review about "{topic}" based ONLY on the provided claims.

AVAILABLE PAPERS (use their citation keys):
{{
{papers_section}
}}

CLAIMS BY EVIDENCE TYPE:
{{
{claims_section}
}}

Return a JSON object with:
- title: review title
- background: list of {{"text": "...", "citations": ["citation_key"]}}
- main_evidence: list of {{"text": "...", "citations": ["citation_key"]}}
- methods_and_models: list of {{"text": "...", "citations": ["citation_key"]}}
- limitations: list of {{"text": "...", "citations": ["citation_key"]}}
- open_questions: list of {{"text": "...", "citations": ["citation_key"]}}
- warnings: list of strings (any issues found)

VALID CITATION KEYS: [{keys_str}]

CRITICAL RULES:
- Return ONLY valid JSON, no markdown fences or explanation.
- EVERY citation must be one of the valid citation keys listed above.
- Do NOT invent claims not present in the provided evidence.
- If a section has no evidence, use an empty list.
- Each text item should synthesize multiple claims when possible.
- Open questions MUST include citations to the papers that raised them."""
