# Mnemosyne / KnowCran

**Status: 1.0.0 production release candidate**

Mnemosyne, packaged as `knowcran`, is a local scientific evidence knowledge base for literature discovery, traceable claim extraction, evidence matrices, review drafting, Obsidian export, and MCP access from agent clients such as Codex, Claude Code, and Claude Desktop.

The project is designed for local-first research workflows. It stores paper metadata, claims, citations, runs, and generated artifacts in SQLite and plain files. Semantic Scholar is the primary discovery source. LLM/agent extraction is optional; deterministic extraction remains the default fallback.

## What 1.0.0 Means

Version 1.0.0 is the first production-baseline release. It does not mean cloud multi-tenancy, full-text PDF ingestion, or polished academic prose generation. It does mean:

- repeatable local install and test workflow
- explicit Apache-2.0 license
- stable CLI entry points: `knowcran` and `mnemosyne`
- readonly, curate, and admin MCP profiles
- evidence traceability through `paper_id`, `claim_id`, `citation_key`, `source_quote`, and `evidence_status`
- SQLite migrations for existing local databases
- cached, rate-limited Semantic Scholar access with retry behavior
- CI-ready unit, integration, MCP, and packaging checks

## Features

| Area | Capability |
| --- | --- |
| Discovery | Search Semantic Scholar, cache raw responses, deduplicate papers, and store topic membership. |
| Reading | Extract claims from abstracts with deterministic fallback and optional agent/LLM providers. |
| Evidence | Build evidence matrices with citation keys, source quotes, evidence status, and coverage summaries. |
| Review | Generate evidence digests and review drafts from stored claims. |
| Obsidian | Export papers, claims, topics, reviews, CSV evidence matrices, and BibTeX. |
| MCP | Serve readonly, curate, and admin MCP profiles for agent clients. |
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

```bash
# Discover literature.
knowcran discover "intracerebral hemorrhage" --limit 100

# Extract claims. Use --limit 0 to process all available topic papers.
knowcran read-topic "intracerebral hemorrhage" --limit 50

# Generate a traceable review draft.
knowcran review "intracerebral hemorrhage" --max-papers 50

# Export Obsidian notes and review artifacts.
knowcran export-obsidian "intracerebral hemorrhage"

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
