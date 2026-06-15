"""Obsidian vault export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowcran.config import VAULT_DIR
from knowcran.storage import Storage
from knowcran.utils import citation_key, paper_note_stem, slugify


def _format_claim_callout(c: dict[str, Any]) -> str:
    etype = c.get("evidence_type", "paragraph")
    conf = c.get("confidence", 0.0)
    text = c.get("claim_text", "").strip()
    
    if etype == "result":
        callout_type = "success"
        title = f"Result (conf: {conf})"
    elif etype == "limitation":
        callout_type = "warning"
        title = f"Limitation (conf: {conf})"
    elif etype == "method":
        callout_type = "info"
        title = f"Method (conf: {conf})"
    elif etype == "open_question":
        callout_type = "question"
        title = f"Open Question (conf: {conf})"
    else:
        callout_type = "note"
        title = f"{etype.replace('_', ' ').title()} (conf: {conf})"
        
    callout = f"> [!{callout_type}] {title}\n"
    for line in text.split("\n"):
        callout += f"> {line}\n"
    return callout + "\n"


def _paper_note(
    paper: dict[str, Any],
    claims: list[dict[str, Any]],
    links: list[dict[str, Any]],
    chunks: list[dict[str, Any]] | None = None,
    citation_key: str = "",
    pdf_path: str | None = None,
    parser_name: str | None = None,
    evidence_status: str = "abstract_only",
    media_assets: list[dict[str, Any]] | None = None,
) -> str:
    chunks_list = chunks or []
    yaml = f"""---
paper_id: {paper['paper_id']}
title: "{paper['title'].replace('"', "'")}"
year: {paper.get('year', '')}
venue: "{paper.get('venue', '') or ''}"
doi: "{paper.get('doi', '') or ''}"
pmid: {paper.get('pmid', '') or ''}
citation_count: {paper.get('citation_count', 0)}
discovered_by: {paper.get('discovered_by', '')}
citation_key: "{citation_key}"
pdf_path: "{pdf_path or ''}"
parser_name: "{parser_name or ''}"
evidence_status: "{evidence_status}"
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
    body += f"- **URL**: {paper.get('url') or 'N/A'}\n"
    if pdf_path:
        body += f"- **PDF Path**: {pdf_path}\n"
    if parser_name:
        body += f"- **Parser**: {parser_name}\n"
    body += f"- **Evidence Status**: {evidence_status}\n\n"

    body += "## Abstract\n\n"
    body += (paper.get("abstract") or "No abstract available.") + "\n\n"

    if claims:
        body += "## Key Claims\n\n"
        for c in claims:
            body += _format_claim_callout(c)

    methods = [c for c in claims if c["evidence_type"] == "method"]
    if methods:
        body += "## Methods\n\n"
        for m in methods:
            body += _format_claim_callout(m)

    limitations = [c for c in claims if c["evidence_type"] == "limitation"]
    if limitations:
        body += "## Limitations\n\n"
        for l in limitations:
            body += _format_claim_callout(l)

    open_qs = [c for c in claims if c["evidence_type"] == "open_question"]
    if open_qs:
        body += "## Open Questions\n\n"
        for q in open_qs:
            body += _format_claim_callout(q)


    if links:
        body += "## Links\n\n"
        for link in links:
            body += f"- {link['link_type']}: {link['target_paper_id']}\n"
        body += "\n"

    if chunks_list:
        body += "## Layout Chunks\n\n"
        for chunk in chunks_list:
            sec_str = f" - {chunk['section']}" if chunk.get("section") else ""
            body += f"- [[{chunk['chunk_id']}|Chunk {chunk['chunk_index']} (Pages {chunk['page_start']}-{chunk['page_end']}{sec_str})]]\n"
        body += "\n"

    if media_assets:
        body += "## Figures and Tables\n\n"
        for m in media_assets:
            label = m.get("figure_label") or m.get("media_type", "media").title()
            body += f"### {label}\n\n"
            
            img_path = m.get("image_path")
            if img_path:
                # Resolve relative path from vault/papers/ to data/runtime/media/
                from pathlib import Path
                parts = Path(img_path).parts
                if len(parts) > 2 and parts[0] == "projects":
                    rel_path = "../../" + "/".join(parts[2:])
                else:
                    rel_path = "../../" + img_path
                body += f"![{label}]({rel_path})\n\n"
                
            if m.get("caption_text"):
                body += f"**Caption**: {m['caption_text']}\n\n"
                
            if m.get("vlm_description"):
                body += f"> [!info] Vision VLM Interpretation\n"
                for line in m["vlm_description"].split("\n"):
                    body += f"> {line}\n"
                body += "\n"
                
            if m.get("media_type") == "table" and m.get("markdown_table"):
                body += "#### Extracted Table Markdown\n\n"
                body += m["markdown_table"] + "\n\n"

    return yaml + body


def _claim_note(claim: dict[str, Any], paper_note_map: dict[str, str] | None = None) -> str:
    extraction_method = claim.get("extraction_method", "deterministic")
    topic = claim.get("topic", "")
    claim_hash = claim.get("claim_hash", "")
    source_location = claim.get("source_location", "")
    citation_key = claim.get("citation_key", "")
    is_placeholder = claim.get("is_placeholder", 0)

    # Check for chunk ID in source span
    chunk_id = None
    source_span = claim.get("source_span_json")
    if source_span:
        try:
            span = json.loads(source_span) if isinstance(source_span, str) else source_span
            chunk_id = span.get("chunk_id")
        except Exception:
            pass

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
    if chunk_id:
        body += f"**Chunk**: [[{chunk_id}]]\n"
    if citation_key:
        body += f"**Citation Key**: `{citation_key}`\n"
    return yaml + body


def _chunk_note(chunk: dict[str, Any], paper_note_stem: str, citation_key: str) -> str:
    yaml = f"""---
chunk_id: {chunk['chunk_id']}
paper_id: {chunk['paper_id']}
page_start: {chunk['page_start']}
page_end: {chunk['page_end']}
section: "{chunk.get('section') or ''}"
chunk_index: {chunk['chunk_index']}
tags:
  - chunk
---"""
    body = f"\n# Chunk {chunk['chunk_index']} (Pages {chunk['page_start']}-{chunk['page_end']})\n\n"
    body += f"**Source**: [[{paper_note_stem}#page={chunk['page_start']}|{citation_key}]]\n\n"
    body += "## Content\n\n"
    body += f"{chunk['text']}\n"
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
        stem = paper_note_stem(p)
        body += f"- [[{stem}|{p['title']}]] ({p.get('year', '?')})\n"
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


def export_obsidian(topic: str, storage: Storage | None = None, vault_dir: Path = VAULT_DIR, limit: int = 1500) -> dict[str, int]:
    own = storage is None
    storage = storage or Storage()
    try:
        resolved_topic = storage.resolve_topic(topic)

        if storage.has_topic_papers(resolved_topic):
            papers = storage.get_topic_papers(resolved_topic, limit=limit)
        elif storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=limit)
        else:
            papers = storage.get_papers_by_topic(topic, limit=limit)
        claims = storage.get_claims_by_topic(topic)

        papers_dir = vault_dir / "papers"
        claims_dir = vault_dir / "claims"
        topics_dir = vault_dir / "topics"
        chunks_dir = vault_dir / "chunks"

        papers_dir.mkdir(parents=True, exist_ok=True)
        claims_dir.mkdir(parents=True, exist_ok=True)
        topics_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)

        paper_note_map: dict[str, str] = {}
        chunks_count = 0

        for p in papers:
            links = storage.get_links(p["paper_id"])
            paper_claims = [c for c in claims if c["paper_id"] == p["paper_id"]]
            stem = paper_note_stem(p)
            paper_note_map[p["paper_id"]] = stem
            filename = f"{stem}.md"
            ckey = citation_key(p)

            # Fetch layout details
            parsed_doc = storage.get_parsed_document(p["paper_id"])
            parser_name = parsed_doc.get("parser_name") if parsed_doc else None

            assets = storage.get_assets_for_paper(p["paper_id"])
            pdf_path = next((a["file_path"] for a in assets if a["status"] == "downloaded"), None)

            has_ft_claim = any(c.get("evidence_status") == "full_text_reviewed" for c in paper_claims)
            evidence_status = "full_text_reviewed" if (has_ft_claim or storage.has_chunks(p["paper_id"])) else "abstract_only"

            # Fetch chunks
            chunks = storage.get_chunks_for_paper(p["paper_id"])
            for chunk in chunks:
                (chunks_dir / f"{chunk['chunk_id']}.md").write_text(_chunk_note(chunk, stem, ckey), encoding="utf-8")
                chunks_count += 1

            # Fetch media assets and attach VLM descriptions
            media_assets = storage.get_media_for_paper(p["paper_id"])
            media_list = []
            for m in media_assets:
                m_copy = dict(m)
                descriptions = storage.get_media_vlm_descriptions(m["media_id"])
                m_copy["vlm_description"] = descriptions[0]["description_text"] if descriptions else ""
                media_list.append(m_copy)

            (papers_dir / filename).write_text(
                _paper_note(p, paper_claims, links, chunks, ckey, pdf_path, parser_name, evidence_status, media_list),
                encoding="utf-8"
            )

        for c in claims:
            (claims_dir / f"{c['claim_id']}.md").write_text(_claim_note(c, paper_note_map), encoding="utf-8")

        (topics_dir / f"{slugify(topic)}.md").write_text(_topic_note(topic, papers, claims), encoding="utf-8")

        return {"papers": len(papers), "claims": len(claims), "topics": 1, "chunks": chunks_count}
    finally:
        if own:
            storage.close()
