"""MCP tool definitions for KnowCran.

Tools are split into two categories:
- Read-only tools: safe for long-running MCP client connections
- Curate/write tools: require approval, may network or mutate data
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations


# ---------------------------------------------------------------------------
# Read-only tool definitions
# ---------------------------------------------------------------------------

def get_read_tools() -> list[dict[str, Any]]:
    """Return read-only MCP tool definitions with annotations."""
    return [
        {
            "name": "knowcran_search_papers",
            "description": "Search papers in the KnowCran database by title or abstract keywords. Returns paper_id, title, year, venue, doi, pmid, citation_key, relevance_score.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (keywords)"},
                    "topic": {"type": "string", "description": "Topic name (alternative to query)"},
                    "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
                    "offset": {"type": "integer", "description": "Pagination offset (default 0)", "default": 0},
                    "response_format": {"type": "string", "enum": ["json", "markdown"], "default": "json", "description": "Response format"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
            },
            "annotations": ToolAnnotations(
                title="Search Papers",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_search_claims",
            "description": "Search claims by topic, paper_id, or evidence_type. Returns claim_id, paper_id, citation_key, claim_text, evidence_type, confidence, source_location, source_quote.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search claims for"},
                    "paper_id": {"type": "string", "description": "Filter by paper ID"},
                    "evidence_type": {"type": "string", "description": "Filter by evidence type (abstract_summary, method, result, limitation, open_question)"},
                    "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
                    "offset": {"type": "integer", "description": "Pagination offset (default 0)", "default": 0},
                    "min_confidence": {"type": "number", "description": "Minimum confidence threshold (0-1)"},
                    "response_format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Search Claims",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_topic_papers",
            "description": "Get papers associated with a topic. Returns paper_id, title, year, venue, relevance_score.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "limit": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "offset": {"type": "integer", "description": "Pagination offset (default 0)", "default": 0},
                    "response_format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Get Topic Papers",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_evidence_matrix",
            "description": "Get the evidence matrix for a topic (papers x claims). Returns claim-level traceability with citation_key, source_quote, evidence_status. Use this for writing reviews or answering questions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "max_papers": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "evidence_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by evidence types"},
                    "include_quotes": {"type": "boolean", "description": "Include source quotes (default true)", "default": True},
                    "include_open_questions": {"type": "boolean", "description": "Include open questions (default true)", "default": True},
                    "response_format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Get Evidence Matrix",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_bibliography",
            "description": "Get BibTeX bibliography or citation key map for a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "format": {"type": "string", "enum": ["bibtex", "json"], "default": "bibtex", "description": "Output format"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Get Bibliography",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_stats",
            "description": "Check KnowCran knowledge base health: paper count, claim count, link count, topic count, last updated.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
            },
            "annotations": ToolAnnotations(
                title="Knowledge Base Stats",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Curate / write tool definitions
# ---------------------------------------------------------------------------

def get_write_tools() -> list[dict[str, Any]]:
    """Return curate/write MCP tool definitions with annotations."""
    return [
        {
            "name": "knowcran_discover",
            "description": "Search Semantic Scholar for papers on a topic and store them in the database. Returns search summary, not conclusions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Research topic or question"},
                    "limit": {"type": "integer", "description": "Max papers (default 50, max 200)", "default": 50},
                    "expand": {"type": "boolean", "description": "Expand via references/citations (default false)", "default": False},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Discover Papers",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        },
        {
            "name": "knowcran_read_topic",
            "description": "Extract claims from all papers matching a topic. Each claim must have source_quote or be marked full_text_needed.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to read"},
                    "limit": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Read Topic Claims",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_read_paper",
            "description": "Extract claims from a single paper by paper_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "topic": {"type": "string", "description": "Topic to tag claims with"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Read Paper Claims",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_review",
            "description": "Generate a literature review from stored claims. Citation keys are validated against the database.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to review"},
                    "max_papers": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                    "vault_dir": {"type": "string", "description": "Vault directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Generate Review",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_export_obsidian",
            "description": "Export Obsidian vault notes for a topic. Only writes to configured vault directory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to export"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                    "vault_dir": {"type": "string", "description": "Vault directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Export to Obsidian",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Audit tool (anti-hallucination)
# ---------------------------------------------------------------------------

def get_audit_tools() -> list[dict[str, Any]]:
    """Return audit/anti-hallucination tool definitions."""
    return [
        {
            "name": "knowcran_audit_answer",
            "description": "Audit an agent-generated answer against the evidence matrix. Flags unsupported facts, invalid citations, overclaim risks (abstract_only_overclaim, animal_to_human_overclaim, correlation_to_causation, missing_uncertainty).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to audit against"},
                    "answer_text": {"type": "string", "description": "The agent-generated answer text to audit"},
                    "strict": {"type": "boolean", "description": "Strict mode: require every fact to have a claim (default false)", "default": False},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic", "answer_text"],
            },
            "annotations": ToolAnnotations(
                title="Audit Answer",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
    ]


def get_all_tools() -> list[dict[str, Any]]:
    """Return all MCP tools (read + write + audit + fulltext)."""
    return get_read_tools() + get_write_tools() + get_audit_tools() + get_fulltext_read_tools() + get_fulltext_write_tools()


# ---------------------------------------------------------------------------
# Fulltext tool definitions
# ---------------------------------------------------------------------------

def get_fulltext_read_tools() -> list[dict[str, Any]]:
    """Return read-only fulltext MCP tool definitions."""
    return [
        {
            "name": "knowcran_search_fulltext",
            "description": "Search fulltext chunks using FTS5. Returns matching text with paper title, year, page range, section, and chunk metadata.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "FTS5 search query"},
                    "topic": {"type": "string", "description": "Scope to topic (optional)"},
                    "paper_id": {"type": "string", "description": "Scope to paper (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["query"],
            },
            "annotations": ToolAnnotations(
                title="Search Fulltext",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_pdf_status",
            "description": "Get PDF download status for a topic or specific paper. Shows download progress, sources, and file paths.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to check status for"},
                    "paper_id": {"type": "string", "description": "Specific paper ID"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
            },
            "annotations": ToolAnnotations(
                title="Get PDF Status",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_paper_note",
            "description": "Get a structured paper note with sections for metadata, methods, results, limitations, and evidence quotes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Get Paper Note",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_evidence_context",
            "description": "Get evidence context for a claim including source quote, page range, and chunk text. Use for citation verification.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string", "description": "Claim ID to get context for"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["claim_id"],
            },
            "annotations": ToolAnnotations(
                title="Get Evidence Context",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_review_artifacts",
            "description": "Get review artifacts (review markdown, evidence matrix CSV, bibliography, open questions) for a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                    "vault_dir": {"type": "string", "description": "Vault directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Get Review Artifacts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_search_fulltext_hybrid",
            "description": "Search fulltext chunks using a hybrid approach combining FTS5 keyword matching and vector similarity. Returns best matching chunks.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "topic": {"type": "string", "description": "Scope search to topic (optional)"},
                    "paper_id": {"type": "string", "description": "Scope search to specific paper ID (optional)"},
                    "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["query"],
            },
            "annotations": ToolAnnotations(
                title="Search Fulltext Hybrid",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_evidence_pack",
            "description": "Retrieve an evidence pack for a topic, including extracted claims, source quotes, bounding boxes, page ranges, and citation keys.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "limit": {"type": "integer", "description": "Max claims (default 50)", "default": 50},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Get Evidence Pack",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_get_page_context",
            "description": "Retrieve chunks from a specific page and adjacent pages (e.g. page-1 to page+1) for a given paper to provide context around a specific page number.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID"},
                    "page_number": {"type": "integer", "description": "Target page number (1-indexed)"},
                    "window": {"type": "integer", "description": "Number of adjacent pages to include (default 1)", "default": 1},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id", "page_number"],
            },
            "annotations": ToolAnnotations(
                title="Get Page Context",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
    ]


def get_fulltext_write_tools() -> list[dict[str, Any]]:
    """Return curate/write fulltext MCP tool definitions."""
    return [
        {
            "name": "knowcran_download_paper_pdf",
            "description": "Download a PDF for a single paper. Tries DOI, arXiv ID, and open access sources. Returns download result with source and file path.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID to download PDF for"},
                    "strategy": {"type": "string", "enum": ["fastest", "oa_first", "legal_only", "scihub_only"], "default": "fastest", "description": "Download strategy"},
                    "force": {"type": "boolean", "default": False, "description": "Force re-download even if cached"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Download Paper PDF",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        },
        {
            "name": "knowcran_download_topic_pdfs",
            "description": "Download PDFs for all papers in a topic. Returns summary of download results.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to download PDFs for"},
                    "limit": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "strategy": {"type": "string", "enum": ["fastest", "oa_first", "legal_only", "scihub_only"], "default": "fastest"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Download Topic PDFs",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        },
        {
            "name": "knowcran_parse_paper_pdf",
            "description": "Parse a downloaded PDF into page-aware text chunks. Returns chunk count and status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID to parse PDF for"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Parse Paper PDF",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_parse_topic_pdfs",
            "description": "Parse all downloaded PDFs for a topic. Returns summary of parse results.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to parse PDFs for"},
                    "limit": {"type": "integer", "description": "Max papers (default 20)", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Parse Topic PDFs",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_read_fulltext",
            "description": "Extract claims from a paper's full text (PDF chunks). Falls back to abstract if no PDF.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID"},
                    "topic": {"type": "string", "description": "Topic to tag claims with"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Read Fulltext Claims",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_review_fulltext",
            "description": "Generate a literature review prioritizing full-text claims. Includes evidence status and source quotes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to review"},
                    "max_papers": {"type": "integer", "description": "Max papers (default 30)", "default": 30},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                    "vault_dir": {"type": "string", "description": "Vault directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Review Fulltext",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_run_topic",
            "description": "Run the full pipeline: discover -> download -> parse -> extract -> notes -> review. Returns structured output directory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic for the pipeline run"},
                    "limit": {"type": "integer", "description": "Max papers (default 50)", "default": 50},
                    "strategy": {"type": "string", "enum": ["fastest", "oa_first", "legal_only", "scihub_only"], "default": "fastest"},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                    "vault_dir": {"type": "string", "description": "Vault directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Run Topic Pipeline",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        },
    ]


def get_read_only_tools() -> list[dict[str, Any]]:
    """Return only read-only tools (read + audit + fulltext read, no write)."""
    return get_read_tools() + get_audit_tools() + get_fulltext_read_tools()


def get_admin_tools() -> list[dict[str, Any]]:
    """Return admin-only MCP tool definitions for local maintenance."""
    return [
        {
            "name": "knowcran_repair_metadata",
            "description": "Admin: inspect a paper for missing metadata and return repair suggestions. Defaults to dry-run.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Paper ID to inspect"},
                    "dry_run": {"type": "boolean", "description": "Do not write changes (default true)", "default": True},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["paper_id"],
            },
            "annotations": ToolAnnotations(
                title="Repair Metadata",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        },
        {
            "name": "knowcran_dedupe_claims",
            "description": "Admin: inspect duplicate claims within a topic and optionally request merge suggestions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to inspect"},
                    "auto_merge": {"type": "boolean", "description": "Automatically merge duplicates (default false)", "default": False},
                    "data_dir": {"type": "string", "description": "Data directory path (optional)"},
                },
                "required": ["topic"],
            },
            "annotations": ToolAnnotations(
                title="Dedupe Claims",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=False,
            ),
        },
    ]


def get_admin_profile_tools() -> list[dict[str, Any]]:
    """Return all tools exposed by the local admin profile."""
    return get_all_tools() + get_admin_tools()
