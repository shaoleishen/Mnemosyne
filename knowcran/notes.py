"""Structured paper notes with linked claims and chunks.

Generates paper notes with sections for metadata, methods, results,
limitations, and evidence quotes. Links notes to claims and PDF chunks.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from knowcran.storage import Storage


def generate_paper_note(
    paper_id: str,
    topic: str | None = None,
    storage: Storage | None = None,
) -> dict[str, Any]:
    """Generate a structured paper note from stored data.

    Creates a note with sections for metadata, methods, results,
    limitations, and evidence quotes. Links to claims and chunks.
    """
    storage = storage or Storage()

    paper = storage.get_paper(paper_id)
    if not paper:
        return {"success": False, "error": f"Paper not found: {paper_id}"}

    claims = storage.get_claims_for_paper(paper_id)
    chunks = storage.get_chunks_for_paper(paper_id)

    # Group claims by evidence type
    claims_by_type: dict[str, list[dict]] = {}
    for claim in claims:
        etype = claim.get("evidence_type", "unknown")
        claims_by_type.setdefault(etype, []).append(claim)

    # Build note sections
    sections = []
    sections.append(f"# {paper.get('title', 'Untitled')}\n")

    # Metadata section
    sections.append("## Metadata\n")
    sections.append(f"- **Paper ID**: {paper_id}")
    if paper.get("doi"):
        sections.append(f"- **DOI**: {paper['doi']}")
    if paper.get("year"):
        sections.append(f"- **Year**: {paper['year']}")
    if paper.get("venue"):
        sections.append(f"- **Venue**: {paper['venue']}")
    if paper.get("citation_count"):
        sections.append(f"- **Citations**: {paper['citation_count']}")
    authors = _parse_authors(paper.get("authors_json"))
    if authors:
        sections.append(f"- **Authors**: {', '.join(authors[:5])}")
    sections.append("")

    # PDF section
    if chunks:
        sections.append("## PDF\n")
        sections.append(f"- **Chunks**: {len(chunks)}")
        pages = set()
        for c in chunks:
            if c.get("page_start"):
                pages.add(c["page_start"])
        if pages:
            sections.append(f"- **Pages**: {min(pages)}-{max(pages)}")
        sections.append("")

    # Abstract section
    abstract = paper.get("abstract")
    if abstract:
        sections.append("## Abstract\n")
        sections.append(abstract + "\n")

    # Methods section
    method_claims = claims_by_type.get("method", [])
    if method_claims:
        sections.append("## Methods\n")
        for claim in method_claims:
            sections.append(f"- {claim['claim_text']}")
        sections.append("")

    # Key Results section
    result_claims = claims_by_type.get("result", [])
    if result_claims:
        sections.append("## Key Results\n")
        for claim in result_claims:
            sections.append(f"- {claim['claim_text']}")
        sections.append("")

    # Limitations section
    limit_claims = claims_by_type.get("limitation", [])
    if limit_claims:
        sections.append("## Limitations\n")
        for claim in limit_claims:
            sections.append(f"- {claim['claim_text']}")
        sections.append("")

    # Evidence Quotes section (from fulltext claims)
    quote_claims = [c for c in claims if c.get("source_quote")]
    if quote_claims:
        sections.append("## Evidence Quotes\n")
        for claim in quote_claims[:10]:
            page_info = ""
            if claim.get("source_location", "").startswith("fulltext:"):
                page_info = f" ({claim['source_location']})"
            sections.append(f"> {claim['source_quote'][:300]}{page_info}")
            sections.append("")

    # Claims section
    if claims:
        sections.append("## Claims\n")
        for claim in claims:
            status = claim.get("evidence_status", "abstract_only")
            sections.append(f"- [{status}] {claim['claim_text'][:200]}")
        sections.append("")

    # Open Questions section
    oq_claims = claims_by_type.get("open_question", [])
    if oq_claims:
        sections.append("## Open Questions\n")
        for claim in oq_claims:
            sections.append(f"- {claim['claim_text']}")
        sections.append("")

    # Links section
    sections.append("## Links\n")
    linked_claim_ids = [c["claim_id"] for c in claims]
    linked_chunk_ids = [c["chunk_id"] for c in chunks]
    if linked_claim_ids:
        sections.append(f"- Claims: {len(linked_claim_ids)}")
    if linked_chunk_ids:
        sections.append(f"- Chunks: {len(linked_chunk_ids)}")
    sections.append("")

    body = "\n".join(sections)

    # Store note
    note_id = str(uuid.uuid4())
    storage.insert_paper_note(
        note_id=note_id,
        paper_id=paper_id,
        title=paper.get("title", "Untitled"),
        body=body,
        topic=topic,
        note_type="paper_summary",
        linked_claim_ids=linked_claim_ids,
        linked_chunk_ids=linked_chunk_ids,
    )

    return {
        "success": True,
        "note_id": note_id,
        "paper_id": paper_id,
        "claim_count": len(claims),
        "chunk_count": len(chunks),
    }


def generate_topic_notes(
    topic: str,
    limit: int = 20,
    storage: Storage | None = None,
) -> dict[str, Any]:
    """Generate notes for all papers in a topic."""
    storage = storage or Storage()
    canonical_topic = storage.resolve_topic(topic)
    papers = storage.get_topic_papers(canonical_topic, limit=limit)

    results = {
        "topic": canonical_topic,
        "total_papers": len(papers),
        "notes_generated": 0,
        "failed": 0,
    }

    for paper in papers:
        result = generate_paper_note(
            paper_id=paper["paper_id"],
            topic=canonical_topic,
            storage=storage,
        )
        if result.get("success"):
            results["notes_generated"] += 1
        else:
            results["failed"] += 1

    return results


def _parse_authors(authors_json: str | None) -> list[str]:
    """Parse authors JSON into a list of names."""
    if not authors_json:
        return []
    try:
        authors = json.loads(authors_json) if isinstance(authors_json, str) else authors_json
        if isinstance(authors, list):
            return [a.get("name", "") for a in authors if a.get("name")]
    except (json.JSONDecodeError, TypeError):
        pass
    return []
