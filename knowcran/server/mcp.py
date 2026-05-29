"""MCP server implementation for KnowCran using the official MCP Python SDK.

Provides three server modes:
- knowcran-readonly: read-only tools + audit (safe for long-running connections)
- knowcran-curate: all tools including discover/read/review/export (requires approval)
- knowcran-admin: all tools + metadata repair/dedupe (local human only)
"""

from __future__ import annotations

import os
import json
import sys
import inspect
from pathlib import Path
from typing import Any, Annotated, Optional, Literal, List
from pydantic import Field

from mcp.server.fastmcp import FastMCP

from knowcran import __version__
from knowcran.server.tools import get_read_only_tools, get_all_tools, get_admin_profile_tools
from knowcran.security import resolve_allowed_data_dir, resolve_allowed_vault_dir


# Hard limits for MCP responses to prevent context overflow
MAX_LIMIT = 500
DEFAULT_LIMIT = 20


def _resolve_db_path(data_dir: str | None) -> Path | None:
    """Resolve database path from optional data_dir parameter."""
    if data_dir:
        return resolve_allowed_data_dir(data_dir) / "knowcran.sqlite"
    return None


def _get_storage(data_dir: str | None = None):
    """Create a Storage instance with optional custom data_dir."""
    from knowcran.storage import Storage
    db_path = _resolve_db_path(data_dir)
    return Storage(db_path=db_path) if db_path else Storage()


def _normalize_limit(limit: int | None, default: int = DEFAULT_LIMIT, hard_cap: int = MAX_LIMIT) -> int:
    """Normalize limit value: 0 means all, positive means cap, enforce hard ceiling."""
    if limit is None or limit <= 0:
        return 0  # 0 = all available (storage layer omits LIMIT)
    return min(limit, hard_cap)


def _has_more_fetched(fetched: int, requested_limit: int) -> bool:
    """Check if there may be more results. Uses limit+1 trick when needed."""
    if requested_limit <= 0:
        return False  # 0 = all, no more
    return fetched >= requested_limit


# ---------------------------------------------------------------------------
# Tool handler implementations
# ---------------------------------------------------------------------------

def _handle_search_papers(params: dict[str, Any]) -> dict[str, Any]:
    storage = _get_storage(params.get("data_dir"))
    try:
        query = params.get("query") or params.get("topic", "")
        limit = _normalize_limit(params.get("limit"))
        offset = params.get("offset", 0)

        # Fetch limit+1 to accurately detect has_more
        fetch_count = limit + 1 if limit > 0 else 0
        papers = storage.get_papers_by_topic(query, limit=fetch_count)
        has_more = _has_more_fetched(len(papers), limit) if limit > 0 else False
        papers = papers[offset:offset + limit] if limit > 0 else papers[offset:]

        result = {
            "papers": papers,
            "count": len(papers),
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
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
        limit = _normalize_limit(params.get("limit"), default=50)
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
        has_more = (offset + limit) < total if limit > 0 else False
        claims = claims[offset:offset + limit] if limit > 0 else claims[offset:]

        result = {
            "claims": claims,
            "count": len(claims),
            "total": total,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
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
        limit = _normalize_limit(params.get("limit"))
        offset = params.get("offset", 0)

        # Fetch limit+1 to accurately detect has_more
        fetch_count = limit + 1 if limit > 0 else 0
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=fetch_count)
        else:
            papers = storage.get_papers_by_topic(topic, limit=fetch_count)

        has_more = _has_more_fetched(len(papers), limit) if limit > 0 else False
        papers = papers[offset:offset + limit] if limit > 0 else papers[offset:]

        result = {
            "papers": papers,
            "count": len(papers),
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        }
        if params.get("response_format") == "markdown":
            result["markdown"] = _papers_to_markdown(papers)
        return result
    finally:
        storage.close()


def _handle_get_evidence_matrix(params: dict[str, Any]) -> dict[str, Any]:
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
        # Build citation key map using the shared helper
        from knowcran.utils import citation_key as gen_citation_key
        citation_key_map = {p["paper_id"]: gen_citation_key(p) for p in papers}

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
                "citation_key": c.get("citation_key") or citation_key_map.get(c["paper_id"]),
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
            "citation_key_map": citation_key_map,
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
    from knowcran.utils import citation_key as gen_citation_key
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
                    "citation_key": gen_citation_key(p),
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
        topic = params["topic"]
        limit = min(params.get("limit", 50), 200)  # Cap at 200

        # Check if topic already has papers (repeated discover)
        canonical_topic = storage.resolve_topic(topic)
        if storage.has_topic_papers(canonical_topic) and not params.get("force", False):
            existing_papers = storage.get_topic_papers(canonical_topic, limit=limit)
            return {
                "papers": [{"paper_id": p["paper_id"], "title": p.get("title", "")} for p in existing_papers],
                "count": len(existing_papers),
                "topic": topic,
                "skipped": True,
                "existing_count": len(existing_papers),
                "message": f"Topic '{canonical_topic}' already has {len(existing_papers)} papers. Use force=true to re-fetch.",
            }

        papers = discover(
            topic,
            limit=limit,
            expand=params.get("expand", False),
            client=client,
            storage=storage,
        )
        return {
            "papers": [{"paper_id": p.paper_id, "title": p.title} for p in papers],
            "count": len(papers),
            "topic": topic,
        }
    finally:
        client.close()
        storage.close()


def _handle_read_topic(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.reading import read_topic
    storage = _get_storage(params.get("data_dir"))
    try:
        limit = _normalize_limit(params.get("limit"))
        claims = read_topic(params["topic"], limit=limit, storage=storage)
        return {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "evidence_type": c.evidence_type,
                    "claim_text": c.claim_text[:200],
                    "confidence": c.confidence,
                    "citation_key": c.citation_key,
                    "evidence_status": c.evidence_status,
                    "source_quote": (c.source_quote or "")[:200],
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
                    "citation_key": c.citation_key,
                    "evidence_status": c.evidence_status,
                    "source_quote": (c.source_quote or "")[:200],
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
        vdir = resolve_allowed_vault_dir(vault_dir) if vault_dir else None
        max_papers = params.get("max_papers", 20)
        if max_papers > 0:
            max_papers = min(max_papers, 500)
        output = review(
            params["topic"],
            max_papers=max_papers,
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
        vdir = resolve_allowed_vault_dir(vault_dir) if vault_dir else None
        counts = export_obsidian(
            params["topic"],
            storage=storage,
            **({"vault_dir": vdir} if vdir else {}),
        )
        return counts
    finally:
        storage.close()


def _handle_audit_answer(params: dict[str, Any]) -> dict[str, Any]:
    """Audit an agent answer against the evidence matrix.

    Supports citation formats: [Key2024], [@Key2024], (Author, 2024), Author2024.
    Detects overclaim risks: correlation_to_causation, animal_to_human_overclaim,
    missing_uncertainty, abstract_only_overclaim.
    """
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

        # Build citation key set and claim lookup
        from knowcran.utils import citation_key as gen_citation_key
        valid_citation_keys = set()
        citation_key_to_claims: dict[str, list[dict]] = {}
        for c in claims:
            ck = c.get("citation_key") or ""
            if ck:
                valid_citation_keys.add(ck)
                citation_key_to_claims.setdefault(ck, []).append(c)

        # Also compute keys from paper metadata
        for p in papers:
            ck = gen_citation_key(p)
            valid_citation_keys.add(ck)

        valid_paper_ids = selected_ids

        # Sentence-level audit
        sentences = [s.strip() for s in answer_text.replace("\n", " ").split(".") if s.strip()]

        supported_claims = []
        unsupported_claims = []
        missing_citations = []
        invalid_citations = []
        overclaim_risks = []

        # Multi-format citation patterns
        import re
        # Matches: [Key2024], [@Key2024], (Author, 2024), Author2024
        citation_patterns = [
            re.compile(r"\[@([A-Za-z]+\d{4}[a-z]?)\]"),      # [@Key2024]
            re.compile(r"\[([A-Za-z]+\d{4}[a-z]?)\]"),       # [Key2024]
            re.compile(r"\(([A-Za-z]+),?\s*(\d{4})\)"),       # (Author, 2024) or (Author 2024)
        ]

        for sentence in sentences:
            found_citations: list[str] = []

            # Check each citation format
            for pattern in citation_patterns:
                for match in pattern.finditer(sentence):
                    if len(match.groups()) == 1:
                        key = match.group(1)
                    else:
                        # (Author, year) format -> Author2024
                        key = f"{match.group(1)}{match.group(2)}"
                    found_citations.append(key)

            if not found_citations:
                # No citation found — check if sentence makes factual claims
                factual_markers = [
                    "shows", "demonstrates", "found", "reported", "suggests",
                    "indicates", "reveals", "increased", "decreased", "improved",
                    "reduced", "associated", "correlated", "significantly",
                ]
                if any(kw in sentence.lower() for kw in factual_markers):
                    if strict:
                        unsupported_claims.append(sentence[:200])
                    else:
                        missing_citations.append(sentence[:200])
            else:
                sentence_supported = False
                for key in found_citations:
                    if key in valid_citation_keys:
                        # Citation exists — check if claim content matches
                        matched_claims = citation_key_to_claims.get(key, [])
                        if matched_claims:
                            sentence_supported = True
                            supported_claims.append({
                                "sentence": sentence[:200],
                                "citation": key,
                                "matched_claim": matched_claims[0]["claim_text"][:150],
                            })
                    else:
                        invalid_citations.append({"sentence": sentence[:200], "citation": key})

        # Overclaim detection
        overclaim_patterns = [
            (r"\b(proves?|definitively|conclusively|undeniably)\b", "correlation_to_causation"),
            (r"\b(in humans|clinical trial|patients? show|human study)\b", "animal_to_human_overclaim"),
            (r"\b(always|never|all patients|100%|no risk|completely safe)\b", "missing_uncertainty"),
        ]
        for pattern, risk_type in overclaim_patterns:
            for sentence in sentences:
                if re.search(pattern, sentence, re.IGNORECASE):
                    # Check if there's supporting evidence for this claim
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

        # Abstract-only overclaim detection
        abstract_only_claims = [
            c for c in claims
            if c.get("evidence_status", "abstract_only") in ("abstract_only", "metadata_only")
        ]
        if abstract_only_claims:
            full_text_markers = [
                "detailed analysis", "in-depth review", "full text",
                "comprehensive review of the literature", "thorough examination",
            ]
            if any(kw in answer_text.lower() for kw in full_text_markers):
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
# New read-only tool handlers
# ---------------------------------------------------------------------------

def _handle_get_topic_tree(params: dict[str, Any]) -> dict[str, Any]:
    """Get the topic hierarchy: canonical topic, aliases, parents, children."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        canonical = storage.resolve_topic(topic)
        aliases = storage.get_topic_aliases(canonical)
        family = storage.get_topic_family(canonical)

        return {
            "topic": topic,
            "canonical_topic": canonical,
            "aliases": aliases,
            "parents": family["parents"],
            "children": family["children"],
            "siblings": family["siblings"],
            "paper_count": len(storage.get_topic_papers(canonical, limit=10000)),
            "claim_count": len(storage.get_claims_by_topic(canonical)),
        }
    finally:
        storage.close()


def _handle_validate_citations(params: dict[str, Any]) -> dict[str, Any]:
    """Validate citation keys in text against the knowledge base."""
    import re
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        text = params["text"]

        # Build valid citation key set
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic)
        else:
            papers = storage.get_papers_by_topic(topic)

        from knowcran.utils import citation_key as gen_citation_key
        valid_keys = set()
        key_to_paper: dict[str, dict] = {}
        for p in papers:
            ck = gen_citation_key(p)
            valid_keys.add(ck)
            key_to_paper[ck] = p

        # Also get keys from claims
        claims = storage.get_claims_by_topic(topic)
        for c in claims:
            ck = c.get("citation_key")
            if ck:
                valid_keys.add(ck)

        # Extract citations from text
        patterns = [
            re.compile(r"\[@([A-Za-z]+\d{4}[a-z]?)\]"),
            re.compile(r"\[([A-Za-z]+\d{4}[a-z]?)\]"),
        ]
        found_keys: list[str] = []
        for pattern in patterns:
            found_keys.extend(m.group(1) if pattern.pattern.startswith(r"\[@") else m.group(1) for m in pattern.finditer(text))

        valid_found = [k for k in found_keys if k in valid_keys]
        invalid_found = [k for k in found_keys if k not in valid_keys]

        # Check for missing citations (sentences with factual claims but no citation)
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        uncited_factual = []
        factual_markers = [
            "shows", "demonstrates", "found", "reported", "suggests",
            "indicates", "reveals", "increased", "decreased",
        ]
        for sentence in sentences:
            has_citation = any(p.search(sentence) for p in patterns)
            if not has_citation and any(kw in sentence.lower() for kw in factual_markers):
                uncited_factual.append(sentence[:200])

        return {
            "topic": topic,
            "total_citations_found": len(found_keys),
            "valid_citations": valid_found,
            "invalid_citations": invalid_found,
            "uncited_factual_sentences": uncited_factual,
            "valid_keys_available": sorted(valid_keys)[:50],
        }
    finally:
        storage.close()


def _handle_get_runs(params: dict[str, Any]) -> dict[str, Any]:
    """List recent runs across all operation types."""
    storage = _get_storage(params.get("data_dir"))
    try:
        limit = params.get("limit", 20)
        # Combine agent runs, llm runs, and CLI runs
        agent_runs = storage.get_agent_runs(limit=limit)
        llm_runs = storage.get_llm_runs(limit=limit)

        # Get CLI runs
        rows = storage.conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        cli_runs = [dict(r) for r in rows]

        # Merge and sort by created_at
        all_runs = []
        for r in agent_runs:
            all_runs.append({"type": "agent", "run_id": r["run_id"], "task_type": r["task_type"],
                             "provider": r["provider"], "status": r["status"],
                             "created_at": r["created_at"], "error": r.get("error")})
        for r in llm_runs:
            all_runs.append({"type": "llm", "run_id": r["run_id"], "task_type": r["task_type"],
                             "provider": r["provider"], "status": r["status"],
                             "created_at": r["created_at"], "error": r.get("error")})
        for r in cli_runs:
            all_runs.append({"type": "cli", "run_id": r["run_id"], "command": r.get("command"),
                             "query": r.get("query"), "created_at": r["created_at"]})

        all_runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"runs": all_runs[:limit], "count": len(all_runs[:limit])}
    finally:
        storage.close()


def _handle_get_run(params: dict[str, Any]) -> dict[str, Any]:
    """Inspect a specific run."""
    storage = _get_storage(params.get("data_dir"))
    try:
        run_id = params["run_id"]

        # Check agent runs
        rows = storage.conn.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
        ).fetchall()
        if rows:
            r = dict(rows[0])
            r["_type"] = "agent"
            return r

        # Check llm runs
        rows = storage.conn.execute(
            "SELECT * FROM llm_runs WHERE run_id = ?", (run_id,)
        ).fetchall()
        if rows:
            r = dict(rows[0])
            r["_type"] = "llm"
            return r

        # Check CLI runs
        rows = storage.conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchall()
        if rows:
            r = dict(rows[0])
            r["_type"] = "cli"
            return r

        return {"error": f"Run '{run_id}' not found."}
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# Admin tool handlers
# ---------------------------------------------------------------------------

def _handle_repair_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """Repair paper metadata (stub — full implementation needs DOI/PMID lookup)."""
    storage = _get_storage(params.get("data_dir"))
    try:
        paper_id = params["paper_id"]
        dry_run = params.get("dry_run", True)
        paper = storage.get_paper(paper_id)
        if not paper:
            return {"error": f"Paper '{paper_id}' not found."}

        # Identify missing fields
        missing = []
        for field in ["doi", "pmid", "abstract", "venue", "citation_count"]:
            if not paper.get(field):
                missing.append(field)

        return {
            "paper_id": paper_id,
            "title": paper.get("title"),
            "missing_fields": missing,
            "dry_run": dry_run,
            "message": f"Found {len(missing)} missing fields. Full repair requires DOI/PMID/Crossref lookup (not yet implemented).",
        }
    finally:
        storage.close()


def _handle_dedupe_claims(params: dict[str, Any]) -> dict[str, Any]:
    """Inspect and optionally merge duplicate claims within a topic."""
    storage = _get_storage(params.get("data_dir"))
    try:
        topic = params["topic"]
        auto_merge = params.get("auto_merge", False)

        canonical = storage.resolve_topic(topic)
        claims = storage.get_claims_by_topic(canonical)

        # Group by claim_hash (same content)
        from knowcran.storage import compute_topic_claim_key
        hash_groups: dict[str, list[dict]] = {}
        for c in claims:
            # Recompute hash for grouping
            claim_obj = type('Claim', (), {
                'paper_id': c['paper_id'],
                'topic': c.get('topic'),
                'evidence_type': c.get('evidence_type'),
                'claim_text': c['claim_text'],
                'source_location': c.get('source_location', 'abstract'),
            })()
            h = compute_topic_claim_key(claim_obj)
            hash_groups.setdefault(h, []).append(c)

        # Find groups with duplicates
        duplicates = {h: group for h, group in hash_groups.items() if len(group) > 1}

        merged_count = 0
        if auto_merge and duplicates:
            for h, group in duplicates.items():
                # Keep the first, delete the rest
                for c in group[1:]:
                    storage.conn.execute("DELETE FROM claims WHERE claim_id = ?", (c["claim_id"],))
                    merged_count += 1
            storage.conn.commit()

        return {
            "topic": canonical,
            "total_claims": len(claims),
            "duplicate_groups": len(duplicates),
            "total_duplicates": sum(len(g) - 1 for g in duplicates.values()),
            "merged": merged_count if auto_merge else 0,
            "details": [
                {"hash": h, "count": len(g), "claim_text": g[0]["claim_text"][:100]}
                for h, g in list(duplicates.items())[:10]
            ],
        }
    finally:
        storage.close()


# ---------------------------------------------------------------------------
# Handler dispatch map
# ---------------------------------------------------------------------------

_TOOL_HANDLERS = {
    # Read-only tools
    "knowcran_search_papers": _handle_search_papers,
    "knowcran_search_claims": _handle_search_claims,
    "knowcran_get_topic_papers": _handle_get_topic_papers,
    "knowcran_get_evidence_matrix": _handle_get_evidence_matrix,
    "knowcran_get_bibliography": _handle_get_bibliography,
    "knowcran_stats": _handle_stats,
    "knowcran_get_topic_tree": _handle_get_topic_tree,
    "knowcran_validate_citations": _handle_validate_citations,
    "knowcran_get_runs": _handle_get_runs,
    "knowcran_get_run": _handle_get_run,
    # Write tools
    "knowcran_discover": _handle_discover,
    "knowcran_read_topic": _handle_read_topic,
    "knowcran_read_paper": _handle_read_paper,
    "knowcran_review": _handle_review,
    "knowcran_export_obsidian": _handle_export_obsidian,
    # Audit tool
    "knowcran_audit_answer": _handle_audit_answer,
    # Admin tools
    "knowcran_repair_metadata": _handle_repair_metadata,
    "knowcran_dedupe_claims": _handle_dedupe_claims,
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
    profile = os.getenv("KNOWCRAN_MCP_PROFILE", "readonly")

    # Enforce profile restrictions
    if profile == "readonly":
        allowed_tools = {t["name"] for t in get_read_only_tools()}
    elif profile == "admin":
        allowed_tools = {t["name"] for t in get_admin_profile_tools()}
    else:
        allowed_tools = {t["name"] for t in get_all_tools()}

    if tool_name not in allowed_tools:
        # Also check backwards compatible mnemosyne names if profile is curate or admin
        if profile != "readonly":
            is_compat = tool_name.replace("knowcran_", "mnemosyne_") in _MNEMOSYNE_HANDLERS or tool_name in _MNEMOSYNE_HANDLERS
        else:
            is_compat = False
        if not is_compat:
            return {"error": f"Tool '{tool_name}' is not allowed in {profile} mode."}

    handler = _TOOL_HANDLERS.get(tool_name) or _MNEMOSYNE_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}

    # Validate and resolve parameters for path safety and readonly restrictions
    try:
        # Enforce readonly mode ignores external data_dir
        if profile == "readonly" and "data_dir" in params:
            params["data_dir"] = None

        if "data_dir" in params:
            params["data_dir"] = str(resolve_allowed_data_dir(params["data_dir"]))

        if "vault_dir" in params:
            params["vault_dir"] = str(resolve_allowed_vault_dir(params["vault_dir"]))
    except ValueError as e:
        return {"error": str(e)}

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
        ck = c.get("citation_key", "")
        ck_str = f" [{ck}]" if ck else ""
        lines.append(f"- [{et}] (conf {conf}){ck_str} {text}")
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
        es = row.get("evidence_status", "")
        es_str = f" ({es})" if es and es != "abstract_only" else ""
        lines.append(f"- **{title}**{ck_str}: [{et}]{es_str} {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastMCP signature and server factory
# ---------------------------------------------------------------------------

def _build_signature_from_schema(input_schema: dict[str, Any]) -> inspect.Signature:
    """Construct an inspect.Signature from JSON Schema properties.

    Maps JSON Schema types to Python types:
    - string -> str (or Literal[...] for enums)
    - integer -> int
    - number -> float
    - boolean -> bool
    - array -> List[str] / List[int] / List
    """
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    params = []
    for field_name, prop in properties.items():
        t = prop.get("type")
        if t == "string":
            if "enum" in prop:
                # Create Literal from enum values using __getitem__
                field_type = Literal[tuple(prop["enum"])]
            else:
                field_type = str
        elif t == "integer":
            field_type = int
        elif t == "number":
            field_type = float
        elif t == "boolean":
            field_type = bool
        elif t == "array":
            items_type = prop.get("items", {}).get("type")
            if items_type == "string":
                field_type = List[str]
            elif items_type == "integer":
                field_type = List[int]
            else:
                field_type = List
        else:
            field_type = Any

        description = prop.get("description", "")
        default_val = prop.get("default")
        is_required = field_name in required

        if is_required:
            annotation = Annotated[field_type, Field(description=description)]
            param = inspect.Parameter(
                name=field_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation
            )
        else:
            annotation = Annotated[Optional[field_type], Field(description=description)]
            param = inspect.Parameter(
                name=field_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=annotation,
                default=default_val
            )
        params.append(param)

    return inspect.Signature(params)


def _create_fastmcp_server(name: str, tools: list[dict[str, Any]]) -> FastMCP:
    """Create a FastMCP server with the given tools registered."""
    server = FastMCP(
        name=name,
        instructions=f"KnowCran {name} MCP server. Provides access to a local scientific knowledge base.",
    )

    # Register each tool via the handler dispatch
    for tool_def in tools:
        tool_name = tool_def["name"]

        def make_handler(tname: str, tdef: dict[str, Any]):
            async def handler(**kwargs: Any) -> str:
                result = handle_tool_call(tname, kwargs)
                return json.dumps(result, default=str, ensure_ascii=False)
            handler.__name__ = tname
            handler.__doc__ = tdef.get("description", "")
            if "inputSchema" in tdef:
                handler.__signature__ = _build_signature_from_schema(tdef["inputSchema"])
            return handler

        server.add_tool(
            make_handler(tool_name, tool_def),
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


def _create_admin_server() -> FastMCP:
    """Create the admin MCP server (all tools + admin tools, local human only)."""
    tools = get_admin_profile_tools()
    return _create_fastmcp_server("knowcran-admin", tools)


def _create_all_tools_server() -> FastMCP:
    """Create the all-tools MCP server (backward compat)."""
    tools = get_all_tools()
    return _create_fastmcp_server("knowcran", tools)


# ---------------------------------------------------------------------------
# Public serve functions (called from CLI)
# ---------------------------------------------------------------------------

def serve_mcp() -> None:
    """Run the all-tools MCP server on stdin/stdout (backward compat)."""
    os.environ["KNOWCRAN_MCP_PROFILE"] = "curate"
    server = _create_all_tools_server()
    server.run(transport="stdio")


def serve_mcp_readonly() -> None:
    """Run the read-only MCP server on stdin/stdout."""
    os.environ["KNOWCRAN_MCP_PROFILE"] = "readonly"
    server = _create_readonly_server()
    server.run(transport="stdio")


def serve_mcp_curate() -> None:
    """Run the curate MCP server on stdin/stdout."""
    os.environ["KNOWCRAN_MCP_PROFILE"] = "curate"
    server = _create_curate_server()
    server.run(transport="stdio")


def serve_mcp_admin() -> None:
    """Run the admin MCP server on stdin/stdout."""
    os.environ["KNOWCRAN_MCP_PROFILE"] = "admin"
    server = _create_admin_server()
    server.run(transport="stdio")
