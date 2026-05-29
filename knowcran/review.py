"""Review generation from stored claims."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from knowcran.bibtex import papers_to_bibtex
from knowcran.config import VAULT_DIR
from knowcran.models import EvidenceMatrixRow, ReviewOutput
from knowcran.storage import Storage
from knowcran.utils import citation_key, slugify


def _group_claims(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        groups.setdefault(c["evidence_type"], []).append(c)
    return groups


# Evidence selection priority: result > method > limitation > abstract_summary > full_text_needed > open_question
_EVIDENCE_PRIORITY = {
    "result": 0,
    "method": 1,
    "limitation": 2,
    "abstract_summary": 3,
    "full_text_needed": 4,
    "open_question": 5,
}

# Normalized open question categories
_OPEN_QUESTION_CATEGORIES = {
    "translational relevance": [
        "translational relevance", "animal model", "in vivo", "in vitro",
        "murine", "rodent", "human relevance",
    ],
    "long-term outcomes": [
        "long-term outcomes", "long-term", "follow-up", "1-year", "chronic",
    ],
    "methods/population missing": [
        "study population", "methodology", "sample size", "population",
    ],
    "full-text limitations needed": [
        "full text review", "full text", "limitations needed",
    ],
}


def _select_evidence(claims: list[dict[str, Any]], max_per_paper: int = 3, max_total: int = 0) -> list[dict[str, Any]]:
    """Select evidence claims with priority ordering and per-paper limits.

    Priority: result > method > limitation > abstract_summary > full_text_needed > open_question
    Max 2-3 claims per paper to avoid single-paper dominance.
    If max_total is 0 or less, automatically scales: min(len(claims), max(50, len(claims) // 2)).
    """
    if max_total <= 0:
        max_total = min(len(claims), max(50, len(claims) // 2))
    # Sort by priority then confidence
    sorted_claims = sorted(
        claims,
        key=lambda c: (_EVIDENCE_PRIORITY.get(c.get("evidence_type", ""), 99), -(c.get("confidence") or 0)),
    )

    selected: list[dict[str, Any]] = []
    per_paper_count: dict[str, int] = {}

    for claim in sorted_claims:
        pid = claim.get("paper_id", "")
        if per_paper_count.get(pid, 0) >= max_per_paper:
            continue
        selected.append(claim)
        per_paper_count[pid] = per_paper_count.get(pid, 0) + 1
        if len(selected) >= max_total:
            break

    return selected


def _normalize_open_questions(claims: list[dict[str, Any]]) -> list[str]:
    """Normalize and deduplicate open questions into standard categories."""
    open_qs = [c["claim_text"] for c in claims if c.get("evidence_type") == "open_question"]
    if not open_qs:
        return ["No open questions identified."]

    matched_categories: dict[str, int] = {}
    unmatched: list[str] = []

    for q in open_qs:
        q_lower = q.lower()
        matched = False
        for category, keywords in _OPEN_QUESTION_CATEGORIES.items():
            if any(kw in q_lower for kw in keywords):
                matched_categories[category] = matched_categories.get(category, 0) + 1
                matched = True
                break
        if not matched:
            unmatched.append(q)

    result: list[str] = []
    for category, count in sorted(matched_categories.items(), key=lambda x: -x[1]):
        result.append(f"{category} (mentioned in {count} papers)")
    # Add up to 2 unique unmatched questions
    for q in unmatched[:2]:
        if q not in result:
            result.append(q)

    return result or ["No open questions identified."]


def _build_review_text(topic: str, papers: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    """Build review text in three-section format: Evidence Digest, Thematic Synthesis, Gap Map."""
    paper_map = {p["paper_id"]: p for p in papers}
    keys = {pid: citation_key(p) for pid, p in paper_map.items()}

    def cite(paper_id: str) -> str:
        return f"[@{keys.get(paper_id, paper_id)}]"

    # Select evidence with priority and per-paper limits
    selected = _select_evidence(claims)
    groups = _group_claims(selected)

    text = f"# Literature Review: {topic}\n\n"
    text += f"Based on analysis of {len(papers)} papers and {len(claims)} claims from the KnowCran knowledge base.\n\n"

    # Section 1: Evidence Digest
    text += "## Evidence Digest\n\n"
    for etype in ["result", "method", "limitation", "abstract_summary"]:
        items = groups.get(etype, [])
        if items:
            text += f"### {etype.replace('_', ' ').title()}\n\n"
            for item in items:
                text += f"- {item['claim_text']} {cite(item['paper_id'])}\n"
            text += "\n"

    full_text_needed = groups.get("full_text_needed", [])
    if full_text_needed:
        text += "### Full Text Review Needed\n\n"
        for ft in full_text_needed[:3]:
            text += f"- {ft['claim_text']} {cite(ft['paper_id'])}\n"
        text += "\n"

    # Section 2: Thematic Synthesis
    text += "## Thematic Synthesis\n\n"
    # Group results by theme (simple keyword clustering)
    results = groups.get("result", [])
    if results:
        # Synthesize key findings
        text += "Key findings across the evidence base:\n\n"
        seen_themes: set[str] = set()
        for r in results:
            # Extract a simple theme from the claim text
            words = set(r["claim_text"].lower().split())
            theme_words = words & {"mortality", "survival", "outcome", "treatment", "surgery", "biomarker", "risk", "diagnosis"}
            theme = ", ".join(sorted(theme_words)[:2]) if theme_words else "general"
            if theme not in seen_themes:
                seen_themes.add(theme)
                text += f"- **{theme.title()}**: {r['claim_text']} {cite(r['paper_id'])}\n"
        text += "\n"
    else:
        text += "Needs evidence.\n\n"

    # Section 3: Gap Map
    text += "## Gap Map\n\n"
    text += "### Open Questions\n\n"
    normalized_qs = _normalize_open_questions(claims)
    for i, q in enumerate(normalized_qs, 1):
        text += f"{i}. {q}\n"
    text += "\n"

    # Limitations summary
    limitations = groups.get("limitation", [])
    if limitations:
        text += "### Known Limitations\n\n"
        for l in limitations[:3]:
            text += f"- {l['claim_text']} {cite(l['paper_id'])}\n"
        text += "\n"

    # References
    text += "## References\n\n"
    for p in papers:
        doi = p.get("doi", "")
        doi_str = f" DOI: {doi}" if doi else ""
        key = citation_key(p)
        text += f"- `@{key}`: {p['title']} ({p.get('year', 'N/A')}). {p.get('venue', '')}{doi_str}\n"

    return text


def _add_review_metadata(text: str, topic: str, papers: list[dict[str, Any]], claims: list[dict[str, Any]], provider: str = "deterministic") -> str:
    """Add run metadata header to review text."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    evidence_types: dict[str, int] = {}
    for c in claims:
        et = c.get("evidence_type", "unknown")
        evidence_types[et] = evidence_types.get(et, 0) + 1

    meta = f"""---
generated_at: {now}
topic: "{topic}"
paper_count: {len(papers)}
claim_count: {len(claims)}
provider: {provider}
evidence_types: {evidence_types}
---

"""
    return meta + text


def _build_review_text_from_llm(
    topic: str,
    papers: list[dict[str, Any]],
    llm_output: dict[str, Any],
) -> str:
    """Render Markdown from validated LLM review synthesis output."""
    paper_map = {p["paper_id"]: p for p in papers}

    def _render_section(items: list[dict[str, Any]]) -> str:
        if not items:
            return "Needs evidence.\n"
        lines = []
        for item in items:
            text = item.get("text", "")
            citations = item.get("citations", [])
            if citations:
                cite_str = " ".join(f"[@{c}]" for c in citations)
                lines.append(f"- {text} {cite_str}")
            else:
                lines.append(f"- {text}")
        return "\n".join(lines) + "\n"

    title = llm_output.get("title", f"Literature Review: {topic}")
    text = f"# {title}\n\n"
    text += f"Based on analysis of {len(papers)} papers from the KnowCran knowledge base.\n\n"

    sections = [
        ("Background", llm_output.get("background", [])),
        ("Main Evidence", llm_output.get("main_evidence", [])),
        ("Methods And Models", llm_output.get("methods_and_models", [])),
        ("Limitations", llm_output.get("limitations", [])),
        ("Open Questions", llm_output.get("open_questions", [])),
    ]

    for section_name, items in sections:
        text += f"## {section_name}\n\n"
        text += _render_section(items)
        text += "\n"

    # Add warnings if any
    warnings = llm_output.get("warnings", [])
    if warnings:
        text += "## Warnings\n\n"
        for w in warnings:
            text += f"- {w}\n"
        text += "\n"

    # References section
    text += "## References\n\n"
    for p in papers:
        doi = p.get("doi", "")
        doi_str = f" DOI: {doi}" if doi else ""
        key = citation_key(p)
        text += f"- `@{key}`: {p['title']} ({p.get('year', 'N/A')}). {p.get('venue', '')}{doi_str}\n"

    return text


def _validate_review_citations(llm_output: dict[str, Any], valid_keys: set[str]) -> list[str]:
    """Validate that all citation keys in LLM review output exist in the selected paper set.

    Returns list of invalid citation keys found.
    """
    invalid_keys: list[str] = []
    sections = ["background", "main_evidence", "methods_and_models", "limitations", "open_questions"]
    for section in sections:
        items = llm_output.get(section, [])
        for item in items:
            for cite_key in item.get("citations", []):
                if cite_key not in valid_keys:
                    invalid_keys.append(cite_key)
    return invalid_keys


def _build_evidence_matrix(papers: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[EvidenceMatrixRow]:
    paper_map = {p["paper_id"]: p for p in papers}
    rows: list[EvidenceMatrixRow] = []
    for c in claims:
        p = paper_map.get(c["paper_id"], {})
        rows.append(EvidenceMatrixRow(
            paper_id=c["paper_id"],
            title=p.get("title", ""),
            year=p.get("year"),
            claim_text=c["claim_text"],
            evidence_type=c["evidence_type"],
            confidence=c["confidence"],
        ))
    return rows


def _write_csv(matrix: list[EvidenceMatrixRow], claims: list[dict[str, Any]] | None = None) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["claim_id", "paper_id", "title", "year", "claim_text", "evidence_type", "confidence"])
    for i, row in enumerate(matrix):
        cid = claims[i].get("claim_id", "") if claims and i < len(claims) else ""
        writer.writerow([cid, row.paper_id, row.title, row.year, row.claim_text, row.evidence_type, row.confidence])
    return buf.getvalue()


def _agent_review_synthesis(
    topic: str,
    papers: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    agent_provider: Any,
    storage: Storage,
) -> str | None:
    """Attempt review synthesis via an agent provider."""
    import uuid
    from knowcran.agents.audit import audit_agent_run
    from knowcran.agents.schemas import AgentTask

    try:
        valid_keys = {citation_key(p) for p in papers}
        citation_keys_map = {p["paper_id"]: citation_key(p) for p in papers}

        task = AgentTask(
            task_id=f"review-{uuid.uuid4().hex[:8]}",
            task_type="review_synthesis",
            topic=topic,
            input_json={
                "topic": topic,
                "papers": papers,
                "claims": claims,
                "citation_keys": citation_keys_map,
            },
            output_schema_name="ReviewSynthesisOutput",
        )
        result = agent_provider.run(task)
        audit_agent_run(task, result, storage)

        if result.status != "ok" or not result.output_json:
            return None

        # Validate citation keys
        invalid_keys = _validate_review_citations(result.output_json, valid_keys)
        if invalid_keys:
            return None

        # Check if agent returned all-empty sections despite having claims
        # This happens with deterministic provider which returns empty lists
        if claims:
            sections = ["background", "main_evidence", "methods_and_models", "limitations", "open_questions"]
            all_empty = all(len(result.output_json.get(s, [])) == 0 for s in sections)
            if all_empty:
                return None  # Force fallback to rule-based review

        return _build_review_text_from_llm(topic, papers, result.output_json)

    except Exception:
        return None


def _build_open_questions(claims: list[dict[str, Any]]) -> str:
    text = "# Open Questions\n\n"
    qs = [c for c in claims if c["evidence_type"] == "open_question"]
    if qs:
        for i, q in enumerate(qs, 1):
            text += f"{i}. {q['claim_text']}\n"
            text += f"   Source: Paper {q['paper_id']}\n\n"
    else:
        text += "No open questions identified.\n"
    return text


def review(
    topic: str,
    max_papers: int = 0,
    storage: Storage | None = None,
    vault_dir: Path = VAULT_DIR,
    llm_provider: Any | None = None,
    agent_provider: Any | None = None,
    include_parent: bool = False,
) -> ReviewOutput:
    own = storage is None
    storage = storage or Storage()
    try:
        # effective_topic: default is user input, only alias changes it
        resolved_topic = storage.resolve_topic(topic)
        effective_topic = resolved_topic

        # Dynamically determine max_papers based on available data
        if max_papers <= 0:
            # Count available papers for this topic
            if storage.has_topic_papers(effective_topic):
                count_rows = storage.conn.execute(
                    "SELECT COUNT(*) FROM topic_papers WHERE topic = ?", (effective_topic,)
                ).fetchone()
                available = count_rows[0] if count_rows else 0
            elif storage.has_topic_papers(topic):
                count_rows = storage.conn.execute(
                    "SELECT COUNT(*) FROM topic_papers WHERE topic = ?", (topic,)
                ).fetchone()
                available = count_rows[0] if count_rows else 0
            else:
                available = 0
            # Use all available papers, cap at 500 max
            max_papers = min(available, 500) if available > 0 else 50

        # Use explicit topic membership if available, fall back to text search
        if storage.has_topic_papers(effective_topic):
            papers = storage.get_topic_papers(effective_topic, limit=max_papers)
        elif storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=max_papers)
        else:
            papers = storage.get_papers_by_topic(topic, limit=max_papers)

        # Only include parent papers if explicitly requested
        if include_parent:
            parent_topics = storage.get_parent_topics(topic)
            for parent in parent_topics:
                parent_papers = storage.get_topic_papers(parent, limit=max_papers // 2)
                existing_ids = {p["paper_id"] for p in papers}
                for pp in parent_papers:
                    if pp["paper_id"] not in existing_ids:
                        papers.append(pp)

        selected_paper_ids = {p["paper_id"] for p in papers}
        # Get claims for the effective topic
        claims = [
            c for c in storage.get_claims_by_topic(effective_topic)
            if c["paper_id"] in selected_paper_ids
        ]
        # Also get claims stored under the original topic if different
        if effective_topic != topic:
            claims.extend([
                c for c in storage.get_claims_by_topic(topic)
                if c["paper_id"] in selected_paper_ids and c["claim_id"] not in {x["claim_id"] for x in claims}
            ])
        paper_ids = [p["paper_id"] for p in papers]

        # Try agent/LLM review synthesis
        review_text = None
        if agent_provider is not None:
            review_text = _agent_review_synthesis(topic, papers, claims, agent_provider, storage)

        if review_text is None and llm_provider is not None:
            try:
                from knowcran.llm.prompts import build_review_prompt
                from knowcran.llm.schemas import ReviewSynthesisOutput

                prompt = build_review_prompt(topic, papers, claims)
                result = llm_provider.call(prompt, task_type="review_synthesis")
                parsed = ReviewSynthesisOutput.model_validate(result)

                # Validate citation keys
                valid_keys = {citation_key(p) for p in papers}
                invalid_keys = _validate_review_citations(result, valid_keys)
                if invalid_keys:
                    raise ValueError(f"LLM used invalid citation keys: {invalid_keys}")

                review_text = _build_review_text_from_llm(topic, papers, result)
            except Exception:
                review_text = None

        # Fallback to deterministic review
        if review_text is None:
            review_text = _build_review_text(topic, papers, claims)

        # Add metadata to review text
        provider_name = "deterministic"
        if agent_provider:
            provider_name = agent_provider.name
        elif llm_provider:
            provider_name = "llm"
        review_text = _add_review_metadata(review_text, topic, papers, claims, provider_name)

        matrix = _build_evidence_matrix(papers, claims)
        csv_text = _write_csv(matrix, claims)
        bibtex = papers_to_bibtex(papers)
        open_qs_text = _build_open_questions(claims)

        slug = slugify(topic)
        reviews_dir = vault_dir / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)

        (reviews_dir / f"{slug}_review.md").write_text(review_text, encoding="utf-8")
        (reviews_dir / f"{slug}_evidence_matrix.csv").write_text(csv_text, encoding="utf-8")
        (reviews_dir / f"{slug}_bibliography.bib").write_text(bibtex, encoding="utf-8")
        (reviews_dir / f"{slug}_open_questions.md").write_text(open_qs_text, encoding="utf-8")

        return ReviewOutput(
            topic=topic,
            review_text=review_text,
            evidence_matrix=matrix,
            open_questions=[q["claim_text"] for q in claims if q["evidence_type"] == "open_question"],
            paper_ids=paper_ids,
        )
    finally:
        if own:
            storage.close()
