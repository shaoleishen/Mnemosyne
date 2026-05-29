"""Obsidian vault export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from knowcran.config import VAULT_DIR
from knowcran.storage import Storage
from knowcran.utils import citation_key, paper_note_stem, slugify


def _paper_note(paper: dict[str, Any], claims: list[dict[str, Any]], links: list[dict[str, Any]], citation_key: str = "") -> str:
    yaml = f"""---
paper_id: {paper['paper_id']}
title: "{paper['title'].replace('"', "'")}"
year: {paper.get('year', '')}
venue: "{paper.get('venue', '') or ''}"
doi: {paper.get('doi', '') or ''}
pmid: {paper.get('pmid', '') or ''}
citation_count: {paper.get('citation_count', 0)}
discovered_by: {paper.get('discovered_by', '')}
citation_key: "{citation_key}"
status: unread
tags:
  - paper
  - semantic-scholar
---"""

    body = f"\n# {paper['title']}\n\n"
    body += "## Metadata\n\n"
    body += f"- **Year**: {paper.get('year') or 'N/A'}\n"
    body += f"- **Venue**: {paper.get('venue') or 'N/A'}\n"
    body += f"- **Citations**: {paper.get('citation_count', 0)}\n"
    body += f"- **DOI**: {paper.get('doi') or 'N/A'}\n"
    body += f"- **PMID**: {paper.get('pmid') or 'N/A'}\n"
    body += f"- **URL**: {paper.get('url') or 'N/A'}\n\n"

    body += "## Abstract\n\n"
    body += (paper.get("abstract") or "No abstract available.") + "\n\n"

    if claims:
        body += "## Key Claims\n\n"
        for c in claims:
            body += f"- **{c['evidence_type']}** (conf {c['confidence']}): {c['claim_text']}\n"
        body += "\n"

    methods = [c for c in claims if c["evidence_type"] == "method"]
    if methods:
        body += "## Methods\n\n"
        for m in methods:
            body += m["claim_text"] + "\n\n"

    limitations = [c for c in claims if c["evidence_type"] == "limitation"]
    if limitations:
        body += "## Limitations\n\n"
        for l in limitations:
            body += l["claim_text"] + "\n\n"

    open_qs = [c for c in claims if c["evidence_type"] == "open_question"]
    if open_qs:
        body += "## Open Questions\n\n"
        for q in open_qs:
            body += f"- {q['claim_text']}\n"
        body += "\n"

    if links:
        body += "## Links\n\n"
        for link in links:
            body += f"- {link['link_type']}: {link['target_paper_id']}\n"
        body += "\n"

    return yaml + body


def _claim_note(claim: dict[str, Any], paper_note_map: dict[str, str] | None = None) -> str:
    extraction_method = claim.get("extraction_method", "deterministic")
    topic = claim.get("topic", "")
    claim_hash = claim.get("claim_hash", "")
    source_location = claim.get("source_location", "")
    citation_key = claim.get("citation_key", "")
    is_placeholder = claim.get("is_placeholder", 0)

    yaml = f"""---
claim_id: {claim['claim_id']}
paper_id: {claim['paper_id']}
evidence_type: {claim['evidence_type']}
confidence: {claim['confidence']}
topic: "{topic}"
claim_hash: "{claim_hash}"
source_location: "{source_location}"
citation_key: "{citation_key}"
extraction_method: {extraction_method}
is_placeholder: {is_placeholder}
tags:
  - claim
  - {claim['evidence_type']}
---"""
    body = f"\n# {claim['evidence_type'].replace('_', ' ').title()}\n\n"
    body += f"{claim['claim_text']}\n\n"
    if paper_note_map and claim["paper_id"] in paper_note_map:
        stem = paper_note_map[claim["paper_id"]]
        body += f"**Source**: [[{stem}]]\n"
    else:
        body += f"**Source**: [[{claim['paper_id']}]]\n"
    if citation_key:
        body += f"**Citation Key**: `{citation_key}`\n"
    return yaml + body


def _topic_note(topic: str, papers: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    slug = slugify(topic)
    yaml = f"""---
topic: "{topic}"
tags:
  - topic
---"""
    body = f"\n# {topic}\n\n"
    body += "## Papers\n\n"
    for p in papers:
        year_slug = f"{p.get('year', 'unknown')}_{slugify(p['title'])}"
        body += f"- [[{year_slug}|{p['title']}]] ({p.get('year', '?')})\n"
    body += "\n## Key Evidence\n\n"
    by_type: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        by_type.setdefault(c["evidence_type"], []).append(c)
    for etype, items in by_type.items():
        body += f"### {etype.replace('_', ' ').title()}\n\n"
        for item in items[:5]:
            body += f"- {item['claim_text']}\n"
        body += "\n"
    return yaml + body


def export_obsidian(topic: str, storage: Storage | None = None, vault_dir: Path = VAULT_DIR) -> dict[str, int]:
    own = storage is None
    storage = storage or Storage()
    try:
        # Resolve topic aliases
        resolved_topic = storage.resolve_topic(topic)

        # Use explicit topic membership if available, fall back to text search
        if storage.has_topic_papers(resolved_topic):
            papers = storage.get_topic_papers(resolved_topic, limit=100)
        elif storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=100)
        else:
            papers = storage.get_papers_by_topic(topic, limit=100)
        claims = storage.get_claims_by_topic(topic)

        papers_dir = vault_dir / "papers"
        claims_dir = vault_dir / "claims"
        topics_dir = vault_dir / "topics"
        papers_dir.mkdir(parents=True, exist_ok=True)
        claims_dir.mkdir(parents=True, exist_ok=True)
        topics_dir.mkdir(parents=True, exist_ok=True)

        paper_note_map: dict[str, str] = {}
        for p in papers:
            links = storage.get_links(p["paper_id"])
            paper_claims = [c for c in claims if c["paper_id"] == p["paper_id"]]
            stem = paper_note_stem(p)
            paper_note_map[p["paper_id"]] = stem
            filename = f"{stem}.md"
            ckey = citation_key(p)
            (papers_dir / filename).write_text(_paper_note(p, paper_claims, links, ckey), encoding="utf-8")

        for c in claims:
            (claims_dir / f"{c['claim_id']}.md").write_text(_claim_note(c, paper_note_map), encoding="utf-8")

        (topics_dir / f"{slugify(topic)}.md").write_text(_topic_note(topic, papers, claims), encoding="utf-8")

        return {"papers": len(papers), "claims": len(claims), "topics": 1}
    finally:
        if own:
            storage.close()
