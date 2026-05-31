# Mnemosyne / KnowCran

**Status: 1.1.0 PDF Knowledge Base release**

Mnemosyne, packaged as `knowcran`, is a local scientific evidence knowledge base for literature discovery, PDF downloading, full-text parsing, traceable claim extraction, evidence matrices, review drafting, Obsidian export, and MCP access from agent clients such as Codex, Claude Code, and Claude Desktop.

The project is designed for local-first research workflows. It stores paper metadata, claims, citations, runs, and generated artifacts in SQLite and plain files. Semantic Scholar is the primary discovery source. LLM/agent extraction is optional; deterministic extraction remains the default fallback.

## What 1.1.0 Adds

Version 1.1.0 adds full PDF knowledge base capabilities:

- PDF downloading from 12 sources (arXiv, Unpaywall, OpenAlex, Semantic Scholar, EuropePMC, PMC, CORE, DOAJ, Crossref, Publishers, LibGen, Sci-Hub)
- PDF parsing into page-aware text chunks with section detection
- Full-text claim extraction with provenance (page, section, chunk, source span)
- SQLite FTS5 full-text search across all parsed PDFs
- Structured paper notes linked to claims and chunks
- Robin-style structured output directories for topic runs
- Literature reviews that prioritize full-text evidence over abstracts

## Features

| Area | Capability |
| --- | --- |
| Discovery | Search Semantic Scholar, cache raw responses, deduplicate papers, and store topic membership. |
| PDF Download | Download PDFs from 12 sources with multi-source racing and caching. |
| PDF Parse | Extract page-aware text chunks with section detection using PyMuPDF. |
| Reading | Extract claims from abstracts or full text with deterministic fallback and optional agent/LLM providers. |
| Full-text Search | Search parsed PDFs using SQLite FTS5 with topic and paper scoping. |
| Evidence | Build evidence matrices with citation keys, source quotes, evidence status, and coverage summaries. |
| Review | Generate evidence digests and review drafts from stored claims, prioritizing full-text evidence. |
| Notes | Generate structured paper notes with sections for metadata, methods, results, and limitations. |
| Obsidian | Export papers, claims, topics, reviews, CSV evidence matrices, and BibTeX. |
| MCP | Serve readonly, curate, and admin MCP profiles with fulltext tools for agent clients. |
| Audit | Validate citations and detect common overclaim risks in generated answers. |

## Installation

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
knowcran init
```

Python 3.12 or newer is required.

## Quick Start

### Recommended: Single Pipeline Command

```bash
# Run the complete pipeline (discover -> download -> parse -> extract -> notes -> review).
knowcran run-topic "intracerebral hemorrhage" --limit 50

# Use legal-only sources (no Sci-Hub/LibGen).
knowcran run-topic "intracerebral hemorrhage" --limit 50 --strategy legal_only

# Skip discovery if papers already exist.
knowcran run-topic "intracerebral hemorrhage" --limit 20 --skip-discover
```

### Step-by-Step Workflow

```bash
# Discover literature.
knowcran discover "intracerebral hemorrhage" --limit 100

# Download PDFs for a topic.
knowcran download-topic "intracerebral hemorrhage" --limit 20 --strategy fastest

# Parse downloaded PDFs into text chunks.
knowcran parse-topic "intracerebral hemorrhage" --limit 20

# Extract claims from full text (falls back to abstract if no PDF).
knowcran read-topic "intracerebral hemorrhage" --limit 50 --fulltext

# Search fulltext chunks.
knowcran search-fulltext "hematoma expansion" --topic "intracerebral hemorrhage"

# Generate a full-text review.
knowcran review "intracerebral hemorrhage" --max-papers 30 --fulltext

# Export Obsidian notes and review artifacts.
knowcran export-obsidian "intracerebral hemorrhage"

# Check PDF download status.
knowcran pdf-status "intracerebral hemorrhage"

# Inspect local database health.
knowcran stats
```

## Configuration

Environment variables are read from `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `SEMANTIC_SCHOLAR_API_KEY` | empty | Optional Semantic Scholar API key. |
| `KNOWCRAN_DATA_DIR` | `data` | Directory for SQLite database and raw API cache. |
| `KNOWCRAN_VAULT_DIR` | `vault` | Directory for Obsidian export. |
| `KNOWCRAN_RATE_LIMIT_SECONDS` | `1.1` | Minimum delay between Semantic Scholar requests. |
| `MNEMOSYNE_PDF_DOWNLOAD_ENABLED` | `true` | Enable PDF downloading. |
| `MNEMOSYNE_PDF_DIR` | `data/pdfs` | Directory for storing downloaded PDFs. |
| `MNEMOSYNE_PDF_STRATEGY` | `fastest` | Download strategy: `fastest`, `oa_first`, `legal_only`, `scihub_only`. |
| `MNEMOSYNE_SCIHUB_ENABLED` | `true` | Enable Sci-Hub as a source. |
| `MNEMOSYNE_LIBGEN_ENABLED` | `true` | Enable LibGen as a source. |
| `MNEMOSYNE_TOR_ENABLED` | `false` | Enable Tor for anonymous downloads. |
| `MNEMOSYNE_PDF_BATCH_WORKERS` | `5` | Number of parallel batch download workers. |
| `MNEMOSYNE_LLM_PROVIDER` | `none` | LLM provider: `none` or `claw`. |
| `MNEMOSYNE_CLAW_BIN` | auto-detect | Optional path to the Claw binary. |
| `MNEMOSYNE_CLAW_MODEL` | `sonnet` | Model label passed to Claw. |
| `MNEMOSYNE_CLAW_PERMISSION_MODE` | `read-only` | Permission mode for Claw subprocess calls. |
| `MNEMOSYNE_CLAW_TIMEOUT_SECONDS` | `600` | Timeout for LLM subprocess calls. |
| `MNEMOSYNE_CLAW_MAX_RETRIES` | `2` | Max retries for LLM subprocess calls. |
| `MNEMOSYNE_LLM_CACHE_DIR` | `data/raw/llm` | Directory for LLM run artifacts. |

## MCP Server Profiles

Use readonly by default for long-running agent sessions.

```bash
# Safe default: read-only queries, evidence matrices, bibliography, and audit tools.
knowcran serve-mcp-readonly

# Curate mode: discovery, reading, review, and export.
knowcran serve-mcp-curate

# Admin mode: local repair and dedupe workflows.
knowcran serve-mcp-admin
```

Client templates are available under `docs/mcp/`:

- `docs/mcp/codex.config.toml.example`
- `docs/mcp/claude-code.mcp.json.example`
- `docs/mcp/claude-desktop.config.json.example`

## Evidence Contract

Mnemosyne treats every generated claim as provisional unless it can be traced to stored evidence. Agent-facing outputs should preserve:

- `paper_id`
- `claim_id`
- `citation_key`
- `claim_text`
- `evidence_type`
- `confidence`
- `source_quote` or `evidence_status`

Abstract-only evidence is explicitly marked. Review and answer generation should not present abstract-only or animal-model evidence as full clinical proof.

## Testing

```bash
pytest -v
pytest --cov=knowcran --cov-report=term-missing
```

The CI workflow runs tests on Linux, macOS, and Windows for Python 3.12 and 3.13, then builds a source distribution and wheel.

## Limitations

- Full-text PDF ingestion is not part of the 1.0.0 release.
- Semantic Scholar metadata can be incomplete or rate-limited.
- Deterministic extraction is conservative and may miss nuanced claims.
- Optional LLM/agent providers must return schema-valid JSON before their output is stored.
- Review output is evidence-controlled drafting support, not a substitute for expert literature review.

## Release Documents

- `CHANGELOG.md`
- `ROADMAP.md`
- `CONTRIBUTING.md`
- `docs/release/1.0.0-checklist.md`

## License

Apache-2.0. See `LICENSE`.
