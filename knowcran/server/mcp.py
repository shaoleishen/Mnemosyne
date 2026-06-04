"""MCP server implementation for KnowCran using the official MCP Python SDK.

Provides three server modes:
- knowcran-readonly: read-only tools + audit (safe for long-running connections)
- knowcran-curate: all tools including discover/read/review/export (requires approval)
- knowcran-admin: local maintenance tools in addition to curate tools
"""

from __future__ import annotations

import json
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from knowcran import __version__
from knowcran.config import Settings
from knowcran.security import resolve_allowed_data_dir, resolve_allowed_vault_dir
from knowcran.server.tools import get_read_only_tools, get_all_tools, get_admin_profile_tools


def _json_schema_annotation(schema: dict[str, Any]) -> Any:
    """Map a small JSON Schema subset to Python annotations for FastMCP."""
    if "enum" in schema:
        values = tuple(schema["enum"])
        if values:
            return Literal.__getitem__(values)
    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list
    if schema_type == "object":
        return dict
    return Any


def _build_signature_from_schema(schema: dict[str, Any]) -> inspect.Signature:
    """Build a keyword-only function signature from a tool input schema."""
    required = set(schema.get("required", []))
    parameters = []
    for name, prop_schema in schema.get("properties", {}).items():
        default = inspect.Parameter.empty if name in required else prop_schema.get("default", None)
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=_json_schema_annotation(prop_schema),
            )
        )
    return inspect.Signature(parameters)


def _resolve_db_path(data_dir: str | None) -> Path | None:
    """Resolve database path from optional data_dir parameter."""
    return resolve_allowed_data_dir(data_dir) / "knowcran.sqlite"


def _get_storage(data_dir: str | None = None):
    """Create a Storage instance with optional custom data_dir."""
    from knowcran.storage import Storage
    db_path = _resolve_db_path(data_dir)
    return Storage(db_path=db_path) if db_path else Storage()


def _settings_from_params(params: dict[str, Any]) -> Settings:
    """Build Settings from MCP params after applying path boundary checks."""
    data_dir = resolve_allowed_data_dir(params.get("data_dir"))
    vault_dir = resolve_allowed_vault_dir(params.get("vault_dir"))
    return Settings(data_dir=data_dir, vault_dir=vault_dir)


# ---------------------------------------------------------------------------
# Tool handler implementations
# ---------------------------------------------------------------------------

def _handle_search_papers(params: dict[str, Any]) -> dict[str, Any]:
    storage = _get_storage(params.get("data_dir"))
    try:
        query = params.get("query") or params.get("topic", "")
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        papers = storage.get_papers_by_topic(query, limit=limit + offset)
        # Apply offset
        papers = papers[offset:offset + limit]
        result = {
            "papers": papers,
            "count": len(papers),
            "has_more": len(papers) == limit,
            "next_offset": offset + limit if len(papers) == limit else None,
        }
        if params.get("response_format") == "markdown":
            result["markdown"] = _papers_to_markdown(papers)
        return result
    finally:
        storage.close()


def _handle_search_claims(params: dict[str, Any]) -> dict[str, Any]:
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        limit = params.get("limit", 50)
        offset = params.get("offset", 0)
        min_confidence = params.get("min_confidence")
        evidence_type = params.get("evidence_type")
        paper_id = params.get("paper_id")

        if paper_id:
            claims = storage.get_claims_for_paper(paper_id)
        else:
            claims = storage.get_claims_by_topic(topic)

        # Apply filters
        if evidence_type:
            claims = [c for c in claims if c.get("evidence_type") == evidence_type]
        if min_confidence is not None:
            claims = [c for c in claims if (c.get("confidence") or 0) >= min_confidence]

        total = len(claims)
        claims = claims[offset:offset + limit]
        result = {
            "claims": claims,
            "count": len(claims),
            "total": total,
            "has_more": offset + limit < total,
            "next_offset": offset + limit if offset + limit < total else None,
        }
        if params.get("response_format") == "markdown":
            result["markdown"] = _claims_to_markdown(claims)
        return result
    finally:
        storage.close()


def _handle_get_topic_papers(params: dict[str, Any]) -> dict[str, Any]:
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=limit + offset)
        else:
            papers = storage.get_papers_by_topic(topic, limit=limit + offset)
        papers = papers[offset:offset + limit]
        result = {
            "papers": papers,
            "count": len(papers),
            "has_more": len(papers) == limit,
            "next_offset": offset + limit if len(papers) == limit else None,
        }
        if params.get("response_format") == "markdown":
            result["markdown"] = _papers_to_markdown(papers)
        return result
    finally:
        storage.close()


def _handle_get_evidence_matrix(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.storage import Storage
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        max_papers = params.get("max_papers", 20)
        evidence_types = params.get("evidence_types")
        include_quotes = params.get("include_quotes", True)

        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=max_papers)
        else:
            papers = storage.get_papers_by_topic(topic, limit=max_papers)

        selected_ids = {p["paper_id"] for p in papers}
        claims = [c for c in storage.get_claims_by_topic(topic) if c["paper_id"] in selected_ids]

        if evidence_types:
            claims = [c for c in claims if c.get("evidence_type") in evidence_types]

        paper_map = {p["paper_id"]: p for p in papers}
        matrix = []
        for c in claims:
            p = paper_map.get(c["paper_id"], {})
            row = {
                "paper_id": c["paper_id"],
                "title": p.get("title", ""),
                "year": p.get("year"),
                "claim_id": c.get("claim_id"),
                "claim_text": c["claim_text"],
                "evidence_type": c.get("evidence_type"),
                "confidence": c.get("confidence"),
                "citation_key": c.get("citation_key"),
                "evidence_status": c.get("evidence_status", "abstract_only"),
            }
            if include_quotes:
                row["source_quote"] = c.get("source_quote", c.get("source_location", ""))
                row["source_span"] = c.get("source_span_json")
            matrix.append(row)

        # Coverage summary
        evidence_type_counts: dict[str, int] = {}
        for c in claims:
            et = c.get("evidence_type", "unknown")
            evidence_type_counts[et] = evidence_type_counts.get(et, 0) + 1

        has_abstract_only = any(
            c.get("evidence_status", "abstract_only") in ("abstract_only", "metadata_only")
            for c in claims
        )

        result = {
            "topic": topic,
            "paper_count": len(papers),
            "claim_count": len(claims),
            "evidence_matrix": matrix,
            "coverage_summary": evidence_type_counts,
            "has_abstract_only_evidence": has_abstract_only,
            "limitations": [] if not has_abstract_only else ["Some claims are based on abstracts only, not full text review."],
        }
        if params.get("response_format") == "markdown":
            result["markdown"] = _evidence_matrix_to_markdown(matrix, topic)
        return result
    finally:
        storage.close()


def _handle_get_bibliography(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.bibtex import papers_to_bibtex
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        fmt = params.get("format", "bibtex")
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic)
        else:
            papers = storage.get_papers_by_topic(topic)

        if fmt == "json":
            bib = []
            for p in papers:
                bib.append({
                    "paper_id": p.get("paper_id"),
                    "citation_key": p.get("citation_key", ""),
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "doi": p.get("doi"),
                    "pmid": p.get("pmid"),
                })
            return {"bibliography": bib, "paper_count": len(papers)}
        else:
            bibtex = papers_to_bibtex(papers)
            return {"bibtex": bibtex, "paper_count": len(papers)}
    finally:
        storage.close()


def _handle_stats(params: dict[str, Any]) -> dict[str, Any]:
    storage = _get_storage(params.get("data_dir"))
    try:
        topics = storage.get_canonical_topics()
        return {
            "papers": storage.count_papers(),
            "claims": storage.count_claims(),
            "links": storage.count_links(),
            "topics": len(topics),
        }
    finally:
        storage.close()


def _handle_discover(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.discovery import discover
    from knowcran.semantic_scholar import SemanticScholarClient
    storage = _get_storage(params.get("data_dir"))
    client = SemanticScholarClient()
    try:
        limit = min(params.get("limit", 50), 200)  # Cap at 200
        papers = discover(
            params["topic"],
            limit=limit,
            expand=params.get("expand", False),
            client=client,
            storage=storage,
        )
        return {
            "papers": [{"paper_id": p.paper_id, "title": p.title} for p in papers],
            "count": len(papers),
            "topic": params["topic"],
        }
    finally:
        client.close()
        storage.close()


def _handle_read_topic(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.reading import read_topic
    storage = _get_storage(params.get("data_dir"))
    try:
        claims = read_topic(params["topic"], limit=params.get("limit", 20), storage=storage)
        return {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "evidence_type": c.evidence_type,
                    "claim_text": c.claim_text[:200],
                    "confidence": c.confidence,
                }
                for c in claims
            ],
            "count": len(claims),
        }
    finally:
        storage.close()


def _handle_read_paper(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.reading import read_paper
    storage = _get_storage(params.get("data_dir"))
    try:
        claims = read_paper(params["paper_id"], topic=params.get("topic"), storage=storage)
        return {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "evidence_type": c.evidence_type,
                    "claim_text": c.claim_text[:200],
                    "confidence": c.confidence,
                }
                for c in claims
            ],
            "count": len(claims),
        }
    finally:
        storage.close()


def _handle_review(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.review import review
    storage = _get_storage(params.get("data_dir"))
    try:
        vault_dir = params.get("vault_dir")
        vdir = resolve_allowed_vault_dir(vault_dir)
        output = review(
            params["topic"],
            max_papers=params.get("max_papers", 20),
            storage=storage,
            vault_dir=vdir,
        )
        return {
            "topic": output.topic,
            "paper_count": len(output.paper_ids),
            "evidence_count": len(output.evidence_matrix),
            "open_questions": output.open_questions,
        }
    finally:
        storage.close()


def _handle_export_obsidian(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.obsidian import export_obsidian
    storage = _get_storage(params.get("data_dir"))
    try:
        vault_dir = params.get("vault_dir")
        vdir = resolve_allowed_vault_dir(vault_dir)
        counts = export_obsidian(
            params["topic"],
            storage=storage,
            vault_dir=vdir,
        )
        return counts
    finally:
        storage.close()


def _handle_audit_answer(params: dict[str, Any]) -> dict[str, Any]:
    """Audit an agent answer against the evidence matrix."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        answer_text = params["answer_text"]
        strict = params.get("strict", False)

        # Get evidence matrix
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=50)
        else:
            papers = storage.get_papers_by_topic(topic, limit=50)

        selected_ids = {p["paper_id"] for p in papers}
        claims = [c for c in storage.get_claims_by_topic(topic) if c["paper_id"] in selected_ids]

        # Build citation key set
        valid_citation_keys = {c.get("citation_key") for c in claims if c.get("citation_key")}
        valid_paper_ids = selected_ids

        # Simple sentence-level audit
        sentences = [s.strip() for s in answer_text.replace("\n", " ").split(".") if s.strip()]

        supported_claims = []
        unsupported_claims = []
        missing_citations = []
        invalid_citations = []
        overclaim_risks = []

        # Check for citation patterns like [Author2023] or (Author, 2023)
        import re
        citation_pattern = re.compile(r"\[([A-Za-z]+\d{4})\]|\(([A-Za-z]+),?\s*(\d{4})\)")

        for sentence in sentences:
            citations = citation_pattern.findall(sentence)
            if not citations:
                # No citation found
                if any(kw in sentence.lower() for kw in ["shows", "demonstrates", "found", "reported", "suggests", "indicates", "reveals"]):
                    if strict:
                        unsupported_claims.append(sentence[:200])
                    else:
                        missing_citations.append(sentence[:200])
            else:
                for match in citations:
                    key = match[0] or f"{match[1]}{match[2]}"
                    if key not in valid_citation_keys:
                        invalid_citations.append({"sentence": sentence[:200], "citation": key})

        # Check for overclaim patterns
        overclaim_patterns = [
            (r"proves|definitively|conclusively", "correlation_to_causation"),
            (r"in humans|clinical trial|patients show", "animal_to_human_overclaim"),
            (r"always|never|all patients|100%", "missing_uncertainty"),
        ]
        for pattern, risk_type in overclaim_patterns:
            for sentence in sentences:
                if re.search(pattern, sentence, re.IGNORECASE):
                    # Check if there's supporting evidence
                    has_support = any(
                        c.get("evidence_type") in ("result", "abstract_summary")
                        and (c.get("confidence") or 0) >= 0.7
                        for c in claims
                    )
                    if not has_support:
                        overclaim_risks.append({
                            "sentence": sentence[:200],
                            "risk_type": risk_type,
                        })

        # Check abstract-only overclaim
        abstract_only_claims = [c for c in claims if c.get("evidence_status", "abstract_only") in ("abstract_only", "metadata_only")]
        if abstract_only_claims and any(kw in answer_text.lower() for kw in ["detailed analysis", "in-depth review", "full text"]):
            overclaim_risks.append({
                "sentence": "Answer references full-text analysis but evidence is abstract-only",
                "risk_type": "abstract_only_overclaim",
            })

        return {
            "topic": topic,
            "total_sentences_audited": len(sentences),
            "supported_claims": supported_claims,
            "unsupported_claims": unsupported_claims,
            "missing_citations": missing_citations,
            "invalid_citations": invalid_citations,
            "overclaim_risks": overclaim_risks,
            "valid_citation_keys_available": sorted(valid_citation_keys),
            "recommended_revision": (
                "Add citations for unsupported claims." if unsupported_claims or missing_citations
                else "Fix invalid citation keys." if invalid_citations
                else "Review overclaim risks." if overclaim_risks
                else "Answer appears well-supported."
            ),
        }
    finally:
        storage.close()


def _handle_repair_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """Admin dry-run metadata repair inspection."""
    storage = _get_storage(params.get("data_dir"))
    try:
        paper_id = params["paper_id"]
        dry_run = params.get("dry_run", True)
        paper = storage.get_paper(paper_id)
        if not paper:
            return {"error": f"Paper not found: {paper_id}"}

        important_fields = ["title", "abstract", "year", "venue", "doi", "pmid", "url"]
        missing_fields = [field for field in important_fields if not paper.get(field)]
        suggestions = []
        if missing_fields:
            suggestions.append(
                "Use DOI, PMID, or Semantic Scholar paper_id to repair metadata in a future admin workflow."
            )
        return {
            "paper_id": paper_id,
            "dry_run": dry_run,
            "missing_fields": missing_fields,
            "repair_applied": False,
            "suggestions": suggestions,
        }
    finally:
        storage.close()


def _normalize_claim_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _handle_dedupe_claims(params: dict[str, Any]) -> dict[str, Any]:
    """Admin duplicate claim inspection."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        auto_merge = params.get("auto_merge", False)
        claims = storage.get_claims_by_topic(topic)
        groups: dict[str, list[dict[str, Any]]] = {}
        for claim in claims:
            groups.setdefault(_normalize_claim_text(claim.get("claim_text", "")), []).append(claim)

        duplicate_groups = [
            {
                "claim_text": group[0].get("claim_text", ""),
                "claim_ids": [claim.get("claim_id") for claim in group],
                "paper_ids": sorted({claim.get("paper_id") for claim in group if claim.get("paper_id")}),
                "count": len(group),
            }
            for group in groups.values()
            if len(group) > 1
        ]

        return {
            "topic": topic,
            "auto_merge": auto_merge,
            "merge_applied": False,
            "total_claims": len(claims),
            "duplicate_groups": duplicate_groups,
        }
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# Fulltext tool handlers
# ---------------------------------------------------------------------------

def _handle_search_fulltext(params: dict[str, Any]) -> dict[str, Any]:
    """Search fulltext chunks using FTS5."""
    from knowcran.fulltext import search_fulltext as do_search
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        results = do_search(
            query=params["query"],
            topic=params.get("topic"),
            paper_id=params.get("paper_id"),
            limit=params.get("limit", 20),
            storage=storage,
            settings=settings,
        )
        return {
            "results": results,
            "count": len(results),
            "query": params["query"],
        }
    finally:
        storage.close()


def _handle_get_pdf_status(params: dict[str, Any]) -> dict[str, Any]:
    """Get PDF download status."""
    from knowcran.fulltext import get_pdf_status as do_status
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return do_status(
            topic=params.get("topic"),
            paper_id=params.get("paper_id"),
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def _handle_get_paper_note(params: dict[str, Any]) -> dict[str, Any]:
    """Get a structured paper note."""
    from knowcran.notes import generate_paper_note
    storage = _get_storage(params.get("data_dir"))
    try:
        result = generate_paper_note(
            paper_id=params["paper_id"],
            storage=storage,
        )
        if result.get("success"):
            notes = storage.get_paper_notes(params["paper_id"])
            if notes:
                return {
                    "success": True,
                    "note": notes[0],
                }
        return result
    finally:
        storage.close()


def _handle_get_evidence_context(params: dict[str, Any]) -> dict[str, Any]:
    """Get evidence context for a claim."""
    storage = _get_storage(params.get("data_dir"))
    try:
        claim_id = params["claim_id"]
        claim = storage.get_claim(claim_id)
        if claim:
            chunk = None
            chunk_id = None
            span = None
            source_span = claim.get("source_span_json")
            if source_span:
                try:
                    span = json.loads(source_span) if isinstance(source_span, str) else source_span
                    if isinstance(span, dict):
                        chunk_id = span.get("chunk_id")
                except (json.JSONDecodeError, TypeError):
                    span = None
            if chunk_id:
                chunk = storage.get_chunk(chunk_id)

            paper = storage.get_paper(claim.get("paper_id")) if claim.get("paper_id") else None
            assets = storage.get_assets_for_paper(claim.get("paper_id")) if claim.get("paper_id") else []
            pdf_asset = next((a for a in assets if a.get("status") == "downloaded"), assets[0] if assets else None)

            return {
                "claim": claim,
                "paper": paper,
                "chunk": chunk,
                "pdf_asset": pdf_asset,
                "source_quote": claim.get("source_quote"),
                "source_span": span,
                "evidence_status": claim.get("evidence_status", "abstract_only"),
            }
        return {"error": f"Claim not found: {claim_id}"}
    finally:
        storage.close()


def _handle_get_review_artifacts(params: dict[str, Any]) -> dict[str, Any]:
    """Get review artifacts for a topic."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        vault_dir = params.get("vault_dir")
        vdir = resolve_allowed_vault_dir(vault_dir)
        from knowcran.utils import slugify
        slug = slugify(topic)
        reviews_dir = vdir / "reviews"

        artifacts = {}
        for name, suffix in [
            ("review", f"{slug}_review.md"),
            ("evidence_matrix", f"{slug}_evidence_matrix.csv"),
            ("bibliography", f"{slug}_bibliography.bib"),
            ("open_questions", f"{slug}_open_questions.md"),
        ]:
            path = reviews_dir / suffix
            if path.exists():
                artifacts[name] = path.read_text(encoding="utf-8")

        return {
            "topic": topic,
            "artifacts": artifacts,
            "found": list(artifacts.keys()),
        }
    finally:
        storage.close()


def _handle_download_paper_pdf(params: dict[str, Any]) -> dict[str, Any]:
    """Download a PDF for a single paper."""
    from knowcran.fulltext import download_paper_pdf
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return download_paper_pdf(
            paper_id=params["paper_id"],
            strategy=params.get("strategy", "fastest"),
            storage=storage,
            settings=settings,
            force=params.get("force", False),
        )
    finally:
        storage.close()


def _handle_download_topic_pdfs(params: dict[str, Any]) -> dict[str, Any]:
    """Download PDFs for all papers in a topic."""
    from knowcran.fulltext import download_topic_pdfs
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return download_topic_pdfs(
            topic=params["topic"],
            limit=params.get("limit", 20),
            strategy=params.get("strategy", "fastest"),
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def _handle_parse_paper_pdf(params: dict[str, Any]) -> dict[str, Any]:
    """Parse a downloaded PDF into text chunks."""
    from knowcran.fulltext import parse_paper_pdf
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return parse_paper_pdf(
            paper_id=params["paper_id"],
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def _handle_parse_topic_pdfs(params: dict[str, Any]) -> dict[str, Any]:
    """Parse all downloaded PDFs for a topic."""
    from knowcran.fulltext import parse_topic_pdfs
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return parse_topic_pdfs(
            topic=params["topic"],
            limit=params.get("limit", 20),
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def _handle_read_fulltext(params: dict[str, Any]) -> dict[str, Any]:
    """Extract claims from a paper's full text."""
    from knowcran.reading import read_paper
    storage = _get_storage(params.get("data_dir"))
    try:
        claims = read_paper(
            params["paper_id"],
            topic=params.get("topic"),
            storage=storage,
            fulltext=True,
        )
        return {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "evidence_type": c.evidence_type,
                    "claim_text": c.claim_text[:200],
                    "confidence": c.confidence,
                    "evidence_status": c.evidence_status,
                    "source_location": c.source_location,
                }
                for c in claims
            ],
            "count": len(claims),
        }
    finally:
        storage.close()


def _handle_review_fulltext(params: dict[str, Any]) -> dict[str, Any]:
    """Generate a literature review prioritizing full-text claims."""
    from knowcran.review import review
    storage = _get_storage(params.get("data_dir"))
    try:
        vault_dir = params.get("vault_dir")
        vdir = resolve_allowed_vault_dir(vault_dir)
        output = review(
            params["topic"],
            max_papers=params.get("max_papers", 30),
            storage=storage,
            vault_dir=vdir,
            fulltext=True,
        )
        return {
            "topic": output.topic,
            "paper_count": len(output.paper_ids),
            "evidence_count": len(output.evidence_matrix),
            "open_questions": output.open_questions,
        }
    finally:
        storage.close()


def _handle_run_topic(params: dict[str, Any]) -> dict[str, Any]:
    """Run the full topic pipeline."""
    from knowcran.workflow import run_topic_workflow
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        return run_topic_workflow(
            topic=params["topic"],
            limit=params.get("limit", 50),
            strategy=params.get("strategy", "fastest"),
            storage=storage,
            settings=settings,
            skip_discover=params.get("skip_discover", False),
            skip_download=params.get("skip_download", False),
            skip_parse=params.get("skip_parse", False),
            skip_review=params.get("skip_review", False),
            fulltext=params.get("fulltext", True),
            gpu=params.get("gpu", False),
        )
    finally:
        storage.close()


def _handle_search_fulltext_hybrid(params: dict[str, Any]) -> dict[str, Any]:
    """Search fulltext chunks using a hybrid approach combining FTS5 keyword matching and vector similarity."""
    from knowcran.fulltext import hybrid_search_chunks as do_hybrid_search
    settings = _settings_from_params(params)
    storage = _get_storage(params.get("data_dir"))
    try:
        results = do_hybrid_search(
            query=params["query"],
            topic=params.get("topic"),
            paper_id=params.get("paper_id"),
            limit=params.get("limit", 20),
            storage=storage,
            settings=settings,
        )
        resp = {
            "results": results,
            "count": len(results),
            "query": params["query"],
        }
        if getattr(results, "degraded_reason", None):
            resp["degraded_reason"] = results.degraded_reason
        return resp
    finally:
        storage.close()


def _handle_get_evidence_pack(params: dict[str, Any]) -> dict[str, Any]:
    """Retrieve an evidence pack for a topic, including claims, page ranges, and contexts."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        limit = params.get("limit", 50)
        canonical_topic = storage.resolve_topic(topic)
        claims = storage.conn.execute(
            "SELECT * FROM claims WHERE topic = ? ORDER BY evidence_type, confidence DESC LIMIT ?",
            (canonical_topic, limit),
        ).fetchall()
        pack = []
        for r in claims:
            c = dict(r)
            paper_id = c.get("paper_id")
            paper = storage.get_paper(paper_id) if paper_id else None
            chunk = None
            chunk_id = None
            source_span = c.get("source_span_json")
            if source_span:
                try:
                    span = json.loads(source_span) if isinstance(source_span, str) else source_span
                    if isinstance(span, dict):
                        chunk_id = span.get("chunk_id")
                except (json.JSONDecodeError, TypeError):
                    pass
            if chunk_id:
                chunk = storage.get_chunk(chunk_id)
            pack.append({
                "claim_id": c.get("claim_id"),
                "paper_id": paper_id,
                "title": paper.get("title") if paper else None,
                "citation_key": c.get("citation_key") or (paper.get("citation_key") if paper else None),
                "claim_text": c.get("claim_text"),
                "evidence_type": c.get("evidence_type"),
                "confidence": c.get("confidence"),
                "source_quote": c.get("source_quote") or c.get("source_location"),
                "source_location": c.get("source_location"),
                "source_span": source_span,
                "evidence_status": c.get("evidence_status", "abstract_only"),
                "chunk_text": chunk.get("text") if chunk else None,
                "page_start": chunk.get("page_start") if chunk else None,
                "page_end": chunk.get("page_end") if chunk else None,
                "section": chunk.get("section") if chunk else None,
            })
        return {
            "topic": canonical_topic,
            "claims": pack,
            "count": len(pack),
        }
    finally:
        storage.close()


def _handle_get_page_context(params: dict[str, Any]) -> dict[str, Any]:
    """Retrieve chunks from a specific page and adjacent pages for a given paper."""
    storage = _get_storage(params.get("data_dir"))
    try:
        paper_id = params["paper_id"]
        page_number = params["page_number"]
        window = params.get("window", 1)
        min_page = max(1, page_number - window)
        max_page = page_number + window

        rows = storage.conn.execute(
            """SELECT * FROM paper_chunks 
               WHERE paper_id = ? AND page_start <= ? AND page_end >= ? 
               ORDER BY chunk_index""",
            (paper_id, max_page, min_page)
        ).fetchall()
        chunks = [dict(r) for r in rows]

        if not chunks:
            rows = storage.conn.execute(
                """SELECT * FROM paper_fulltext_chunks 
                   WHERE paper_id = ? AND page_start <= ? AND page_end >= ? 
                   ORDER BY chunk_index""",
                (paper_id, max_page, min_page)
            ).fetchall()
            chunks = [dict(r) for r in rows]

        return {
            "paper_id": paper_id,
            "page_number": page_number,
            "window": window,
            "chunks": chunks,
            "count": len(chunks),
        }
    finally:
        storage.close()


def _handle_answer_rag(params: dict[str, Any]) -> dict[str, Any]:
    """Answer a question using multimodal RAG with evidence from scientific papers."""
    storage = _get_storage(params.get("data_dir"))
    try:
        from knowcran.config import Settings
        from knowcran.rag import run_rag_query

        settings = _settings(params.get("data_dir"))
        query = params["query"]
        topic = params.get("topic")
        paper_id = params.get("paper_id")
        limit = params.get("limit", 20)

        result = run_rag_query(
            query=query,
            topic=topic,
            paper_id=paper_id,
            storage=storage,
            settings=settings,
        )

        return result
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# Vision / Multimodal handlers
# ---------------------------------------------------------------------------

def _handle_describe_figure(params: dict[str, Any]) -> dict[str, Any]:
    """Describe a figure or table image using Vision API."""
    media_id = params.get("media_id")
    image_path = params.get("image_path")
    task_type = params.get("task_type", "describe_media")
    prompt = params.get("prompt")
    settings = _settings_from_params(params)

    # Resolve image path from media_id if needed
    if not image_path and media_id:
        storage = _get_storage(params.get("data_dir"))
        try:
            asset = storage.get_media_asset(media_id)
            if not asset:
                return {"error": f"Media asset not found: {media_id}"}
            image_path = asset.get("image_path", "")
        finally:
            storage.close()

    if not image_path:
        return {"error": "Either media_id or image_path is required"}

    # Get Vision Router
    router = settings.get_vision_router()
    if router is None:
        return {
            "error": "No Vision API provider configured. "
                     "Set MNEMOSYNE_VISION_PROVIDERS and provider-specific env vars."
        }

    result = router.describe_media(
        image_path=image_path,
        task_type=task_type,
        prompt=prompt,
    )

    # Store VLM description if successful and we have a media_id
    if result.get("status") == "success" and media_id:
        storage = _get_storage(params.get("data_dir"))
        try:
            import uuid
            storage.insert_media_vlm_description(
                description_id=str(uuid.uuid4()),
                media_id=media_id,
                provider=result.get("provider", "unknown"),
                model=result.get("model", "unknown"),
                description_text=result.get("description", ""),
                source_type=result.get("source_type", "auxiliary_interpretation"),
                status="success",
            )
        finally:
            storage.close()

    return {
        "description": result.get("description", ""),
        "provider": result.get("provider", "unknown"),
        "model": result.get("model", "unknown"),
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "source_type": result.get("source_type", "auxiliary_interpretation"),
        "media_id": media_id,
        "image_path": image_path,
    }


def _handle_extract_table_markdown(params: dict[str, Any]) -> dict[str, Any]:
    """Extract table from image to Markdown using Vision API."""
    media_id = params.get("media_id")
    image_path = params.get("image_path")
    prompt = params.get("prompt")
    settings = _settings_from_params(params)

    # Resolve image path from media_id if needed
    if not image_path and media_id:
        storage = _get_storage(params.get("data_dir"))
        try:
            asset = storage.get_media_asset(media_id)
            if not asset:
                return {"error": f"Media asset not found: {media_id}"}
            image_path = asset.get("image_path", "")
        finally:
            storage.close()

    if not image_path:
        return {"error": "Either media_id or image_path is required"}

    # Get Vision Router
    router = settings.get_vision_router()
    if router is None:
        return {
            "error": "No Vision API provider configured. "
                     "Set MNEMOSYNE_VISION_PROVIDERS and provider-specific env vars."
        }

    result = router.describe_media(
        image_path=image_path,
        task_type="table_to_markdown",
        prompt=prompt,
    )

    # Store VLM description if successful and we have a media_id
    if result.get("status") == "success" and media_id:
        storage = _get_storage(params.get("data_dir"))
        try:
            import uuid
            storage.insert_media_vlm_description(
                description_id=str(uuid.uuid4()),
                media_id=media_id,
                provider=result.get("provider", "unknown"),
                model=result.get("model", "unknown"),
                description_text=result.get("description", ""),
                source_type="machine_extracted_table",
                status="success",
            )
            # Also update markdown_table field on the asset
            storage.conn.execute(
                "UPDATE parsed_media_assets SET markdown_table = ? WHERE media_id = ?",
                (result.get("description", ""), media_id),
            )
            storage.conn.commit()
        finally:
            storage.close()

    return {
        "markdown": result.get("description", ""),
        "provider": result.get("provider", "unknown"),
        "model": result.get("model", "unknown"),
        "status": result.get("status", "error"),
        "error": result.get("error"),
        "media_id": media_id,
        "image_path": image_path,
    }


def _handle_get_media_assets(params: dict[str, Any]) -> dict[str, Any]:
    """Get all media assets for a paper."""
    paper_id = params.get("paper_id", "")
    if not paper_id:
        return {"error": "paper_id is required"}

    storage = _get_storage(params.get("data_dir"))
    try:
        assets = storage.get_media_for_paper(paper_id)
        result = []
        for a in assets:
            mid = a.get("media_id", "")
            # Attach VLM descriptions if available
            vlm_descriptions = storage.get_media_vlm_descriptions(mid)
            result.append({
                "media_id": mid,
                "media_type": a.get("media_type"),
                "figure_label": a.get("figure_label"),
                "caption_text": a.get("caption_text"),
                "image_path": a.get("image_path"),
                "page_number": a.get("page_number"),
                "markdown_table": a.get("markdown_table"),
                "extraction_method": a.get("extraction_method"),
                "vlm_descriptions": [
                    {
                        "provider": d.get("provider"),
                        "model": d.get("model"),
                        "description_text": d.get("description_text"),
                        "source_type": d.get("source_type"),
                    }
                    for d in vlm_descriptions
                ],
            })
        return {"paper_id": paper_id, "media_count": len(result), "assets": result}
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# Handler dispatch map
# ---------------------------------------------------------------------------

_TOOL_HANDLERS = {
    "knowcran_search_papers": _handle_search_papers,
    "knowcran_search_claims": _handle_search_claims,
    "knowcran_get_topic_papers": _handle_get_topic_papers,
    "knowcran_get_evidence_matrix": _handle_get_evidence_matrix,
    "knowcran_get_bibliography": _handle_get_bibliography,
    "knowcran_stats": _handle_stats,
    "knowcran_discover": _handle_discover,
    "knowcran_read_topic": _handle_read_topic,
    "knowcran_read_paper": _handle_read_paper,
    "knowcran_review": _handle_review,
    "knowcran_export_obsidian": _handle_export_obsidian,
    "knowcran_audit_answer": _handle_audit_answer,
    "knowcran_repair_metadata": _handle_repair_metadata,
    "knowcran_dedupe_claims": _handle_dedupe_claims,
    # Fulltext tools
    "knowcran_search_fulltext": _handle_search_fulltext,
    "knowcran_get_pdf_status": _handle_get_pdf_status,
    "knowcran_get_paper_note": _handle_get_paper_note,
    "knowcran_get_evidence_context": _handle_get_evidence_context,
    "knowcran_get_review_artifacts": _handle_get_review_artifacts,
    "knowcran_download_paper_pdf": _handle_download_paper_pdf,
    "knowcran_download_topic_pdfs": _handle_download_topic_pdfs,
    "knowcran_parse_paper_pdf": _handle_parse_paper_pdf,
    "knowcran_parse_topic_pdfs": _handle_parse_topic_pdfs,
    "knowcran_read_fulltext": _handle_read_fulltext,
    "knowcran_review_fulltext": _handle_review_fulltext,
    "knowcran_run_topic": _handle_run_topic,
    "knowcran_search_fulltext_hybrid": _handle_search_fulltext_hybrid,
    "knowcran_get_evidence_pack": _handle_get_evidence_pack,
    "knowcran_get_page_context": _handle_get_page_context,
    "knowcran_answer_rag": _handle_answer_rag,
    # Vision / Multimodal tools
    "knowcran_describe_figure": _handle_describe_figure,
    "knowcran_extract_table_markdown": _handle_extract_table_markdown,
    "knowcran_get_media_assets": _handle_get_media_assets,
}

# Legacy handler names (backward compat)
_MNEMOSYNE_HANDLERS = {
    "mnemosyne_search_papers": _handle_search_papers,
    "mnemosyne_search_claims": _handle_search_claims,
    "mnemosyne_get_topic_papers": _handle_get_topic_papers,
    "mnemosyne_get_evidence_matrix": _handle_get_evidence_matrix,
    "mnemosyne_get_bibliography": _handle_get_bibliography,
    "mnemosyne_stats": _handle_stats,
    "mnemosyne_discover": _handle_discover,
    "mnemosyne_read_topic": _handle_read_topic,
    "mnemosyne_read_paper": _handle_read_paper,
    "mnemosyne_review": _handle_review,
    "mnemosyne_export_obsidian": _handle_export_obsidian,
}

_MNEMOSYNE_TOOL_ALIASES = {
    name: name.replace("mnemosyne_", "knowcran_", 1)
    for name in _MNEMOSYNE_HANDLERS
}


def _allowed_tool_names(profile: str) -> set[str]:
    from knowcran.server.tools import get_admin_profile_tools, get_all_tools, get_read_only_tools

    if profile == "readonly":
        return {tool["name"] for tool in get_read_only_tools()}
    if profile == "admin":
        return {tool["name"] for tool in get_admin_profile_tools()}
    return {tool["name"] for tool in get_all_tools()}


def handle_tool_call(tool_name: str, params: dict[str, Any], profile: str | None = None) -> dict[str, Any]:
    """Handle an MCP tool call (legacy interface for tests)."""
    active_profile = profile or os.getenv("KNOWCRAN_MCP_PROFILE", "curate")
    canonical_tool_name = _MNEMOSYNE_TOOL_ALIASES.get(tool_name, tool_name)
    if canonical_tool_name.startswith("knowcran_") and canonical_tool_name not in _allowed_tool_names(active_profile):
        return {"error": f"Tool not allowed in {active_profile} profile: {tool_name}"}
    handler = _TOOL_HANDLERS.get(tool_name) or _MNEMOSYNE_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return handler(params)
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Markdown formatting helpers
# ---------------------------------------------------------------------------

def _papers_to_markdown(papers: list[dict]) -> str:
    if not papers:
        return "No papers found."
    lines = []
    for p in papers:
        year = p.get("year", "?")
        title = p.get("title", "Untitled")
        venue = p.get("venue", "")
        pid = p.get("paper_id", "")
        lines.append(f"- **{title}** ({year}) {venue} [ID: {pid}]")
    return "\n".join(lines)


def _claims_to_markdown(claims: list[dict]) -> str:
    if not claims:
        return "No claims found."
    lines = []
    for c in claims:
        et = c.get("evidence_type", "?")
        conf = c.get("confidence", "?")
        text = c.get("claim_text", "")[:150]
        lines.append(f"- [{et}] (conf {conf}) {text}")
    return "\n".join(lines)


def _evidence_matrix_to_markdown(matrix: list[dict], topic: str) -> str:
    if not matrix:
        return f"No evidence found for topic: {topic}"
    lines = [f"# Evidence Matrix: {topic}\n"]
    for row in matrix:
        title = row.get("title", "Unknown")[:60]
        et = row.get("evidence_type", "?")
        conf = row.get("confidence", "?")
        text = row.get("claim_text", "")[:120]
        ck = row.get("citation_key", "")
        ck_str = f" [{ck}]" if ck else ""
        lines.append(f"- **{title}**{ck_str}: [{et}] {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastMCP server factory
# ---------------------------------------------------------------------------

def _create_fastmcp_server(name: str, tools: list[dict[str, Any]], profile: str) -> FastMCP:
    """Create a FastMCP server with the given tools registered."""
    server = FastMCP(
        name=name,
        instructions=f"KnowCran {name} MCP server. Provides access to a local scientific knowledge base.",
    )

    # Register each tool via the handler dispatch
    for tool_def in tools:
        tool_name = tool_def["name"]

        def make_handler(tname: str, schema: dict[str, Any]):
            async def handler(**kwargs: Any) -> str:
                result = handle_tool_call(tname, kwargs, profile=profile)
                return json.dumps(result, default=str, ensure_ascii=False)
            handler.__name__ = tname
            handler.__doc__ = tool_def.get("description", "")
            handler.__signature__ = _build_signature_from_schema(schema)
            return handler

        server.add_tool(
            make_handler(tool_name, tool_def.get("inputSchema", {})),
            name=tool_name,
            description=tool_def.get("description", ""),
            annotations=tool_def.get("annotations"),
        )

    return server


def _create_readonly_server() -> FastMCP:
    """Create the read-only MCP server (safe for long-running connections)."""
    tools = get_read_only_tools()
    return _create_fastmcp_server("knowcran-readonly", tools, profile="readonly")


def _create_curate_server() -> FastMCP:
    """Create the curate MCP server (all tools, requires approval)."""
    tools = get_all_tools()
    return _create_fastmcp_server("knowcran-curate", tools, profile="curate")


def _create_admin_server() -> FastMCP:
    """Create the admin MCP server (local human maintenance only)."""
    tools = get_admin_profile_tools()
    return _create_fastmcp_server("knowcran-admin", tools, profile="admin")


def _create_all_tools_server() -> FastMCP:
    """Create the all-tools MCP server (backward compat)."""
    tools = get_all_tools()
    return _create_fastmcp_server("knowcran", tools, profile="curate")


# ---------------------------------------------------------------------------
# Public serve functions (called from CLI)
# ---------------------------------------------------------------------------

def serve_mcp() -> None:
    """Run the all-tools MCP server on stdin/stdout (backward compat)."""
    server = _create_all_tools_server()
    server.run(transport="stdio")


def serve_mcp_readonly() -> None:
    """Run the read-only MCP server on stdin/stdout."""
    server = _create_readonly_server()
    server.run(transport="stdio")


def serve_mcp_curate() -> None:
    """Run the curate MCP server on stdin/stdout."""
    server = _create_curate_server()
    server.run(transport="stdio")


def serve_mcp_admin() -> None:
    """Run the admin MCP server on stdin/stdout."""
    server = _create_admin_server()
    server.run(transport="stdio")
