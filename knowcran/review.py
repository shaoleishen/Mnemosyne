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


def _build_review_text(topic: str, papers: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    groups = _group_claims(claims)
    paper_map = {p["paper_id"]: p for p in papers}
    keys = {pid: citation_key(p) for pid, p in paper_map.items()}

    def cite(paper_id: str) -> str:
        return f"[@{keys.get(paper_id, paper_id)}]"

    text = f"# Literature Review: {topic}\n\n"
    text += f"Based on analysis of {len(papers)} papers from the KnowCran knowledge base.\n\n"

    text += "## Background\n\n"
    summaries = groups.get("abstract_summary", [])
    if summaries:
        for s in summaries[:5]:
            text += f"- {s['claim_text']} {cite(s['paper_id'])}\n"
    else:
        text += "Needs evidence.\n"
    text += "\n"

    text += "## Main Evidence\n\n"
    results = groups.get("result", [])
    if results:
        for r in results[:8]:
            text += f"- {r['claim_text']} {cite(r['paper_id'])}\n"
    else:
        text += "Needs evidence.\n"
    text += "\n"

    text += "## Methods And Models\n\n"
    methods = groups.get("method", [])
    if methods:
        for m in methods[:5]:
            text += f"- {m['claim_text']} {cite(m['paper_id'])}\n"
    else:
        text += "Needs evidence.\n"
    text += "\n"

    text += "## Limitations\n\n"
    limitations = groups.get("limitation", [])
    if limitations:
        for l in limitations[:5]:
            text += f"- {l['claim_text']} {cite(l['paper_id'])}\n"
    else:
        text += "Needs evidence.\n"
    text += "\n"

    full_text_needed = groups.get("full_text_needed", [])
    if full_text_needed:
        text += "### Full Text Review Needed\n\n"
        for ft in full_text_needed[:5]:
            text += f"- {ft['claim_text']} {cite(ft['paper_id'])}\n"
        text += "\n"

    text += "## Open Questions\n\n"
    open_qs = groups.get("open_question", [])
    if open_qs:
        for q in open_qs[:5]:
            text += f"- {q['claim_text']} {cite(q['paper_id'])}\n"
    else:
        text += "Needs evidence.\n"
    text += "\n"

    text += "## References\n\n"
    for p in papers:
        doi = p.get("doi", "")
        doi_str = f" DOI: {doi}" if doi else ""
        key = citation_key(p)
        text += f"- `@{key}`: {p['title']} ({p.get('year', 'N/A')}). {p.get('venue', '')}{doi_str}\n"

    return text


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


def review(topic: str, max_papers: int = 20, storage: Storage | None = None, vault_dir: Path = VAULT_DIR) -> ReviewOutput:
    own = storage is None
    storage = storage or Storage()
    try:
        # Use explicit topic membership if available, fall back to text search
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=max_papers)
        else:
            papers = storage.get_papers_by_topic(topic, limit=max_papers)
        selected_paper_ids = {p["paper_id"] for p in papers}
        claims = [
            c for c in storage.get_claims_by_topic(topic)
            if c["paper_id"] in selected_paper_ids
        ]
        paper_ids = [p["paper_id"] for p in papers]

        review_text = _build_review_text(topic, papers, claims)
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
