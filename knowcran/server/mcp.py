"""MCP server implementation for KnowCran using the official MCP Python SDK.

Provides two server modes:
- knowcran-readonly: read-only tools + audit (safe for long-running connections)
- knowcran-curate: all tools including discover/read/review/export (requires approval)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from knowcran import __version__
from knowcran.server.tools import get_read_only_tools, get_all_tools


def _resolve_db_path(data_dir: str | None) -> Path | None:
    """Resolve database path from optional data_dir parameter."""
    if data_dir:
        return Path(data_dir) / "knowcran.sqlite"
    return None


def _get_storage(data_dir: str | None = None):
    """Create a Storage instance with optional custom data_dir."""
    from knowcran.storage import Storage
    db_path = _resolve_db_path(data_dir)
    return Storage(db_path=db_path) if db_path else Storage()


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
        vdir = Path(vault_dir) if vault_dir else None
        output = review(
            params["topic"],
            max_papers=params.get("max_papers", 20),
            storage=storage,
            **({"vault_dir": vdir} if vdir else {}),
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
        vdir = Path(vault_dir) if vault_dir else None
        counts = export_obsidian(
            params["topic"],
            storage=storage,
            **({"vault_dir": vdir} if vdir else {}),
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


def handle_tool_call(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle an MCP tool call (legacy interface for tests)."""
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

def _create_fastmcp_server(name: str, tools: list[dict[str, Any]]) -> FastMCP:
    """Create a FastMCP server with the given tools registered."""
    server = FastMCP(
        name=name,
        instructions=f"KnowCran {name} MCP server. Provides access to a local scientific knowledge base.",
    )

    # Register each tool via the handler dispatch
    for tool_def in tools:
        tool_name = tool_def["name"]

        def make_handler(tname: str):
            async def handler(**kwargs: Any) -> str:
                result = handle_tool_call(tname, kwargs)
                return json.dumps(result, default=str, ensure_ascii=False)
            handler.__name__ = tname
            handler.__doc__ = tool_def.get("description", "")
            return handler

        server.add_tool(
            make_handler(tool_name),
            name=tool_name,
            description=tool_def.get("description", ""),
            annotations=tool_def.get("annotations"),
        )

    return server


def _create_readonly_server() -> FastMCP:
    """Create the read-only MCP server (safe for long-running connections)."""
    tools = get_read_only_tools()
    return _create_fastmcp_server("knowcran-readonly", tools)


def _create_curate_server() -> FastMCP:
    """Create the curate MCP server (all tools, requires approval)."""
    tools = get_all_tools()
    return _create_fastmcp_server("knowcran-curate", tools)


def _create_all_tools_server() -> FastMCP:
    """Create the all-tools MCP server (backward compat)."""
    tools = get_all_tools()
    return _create_fastmcp_server("knowcran", tools)


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
