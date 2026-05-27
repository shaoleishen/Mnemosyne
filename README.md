# Mnemosyne

**Status: Alpha (v0.1.0-alpha)**

Local scientific discovery knowledge base using Semantic Scholar.

## Why Not Edison?

KnowCran avoids dependency on Edison, Future House, or any closed-source agent platform. All data retrieval uses the open Semantic Scholar API, and claim extraction is deterministic (no LLM required for v1). This ensures reproducibility, no vendor lock-in, and full local control of your research data.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
# Edit .env to set SEMANTIC_SCHOLAR_API_KEY (optional)
knowcran init
```

## Configuration

Environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_SCHOLAR_API_KEY` | (empty) | Semantic Scholar API key. Optional for low-frequency use. |
| `KNOWCRAN_DATA_DIR` | `data` | Directory for SQLite DB and raw API cache. |
| `KNOWCRAN_VAULT_DIR` | `vault` | Directory for Obsidian markdown export. |
| `KNOWCRAN_RATE_LIMIT_SECONDS` | `1.1` | Seconds between API requests (must be > 1.0). |

## CLI Examples

```bash
# Search for papers on celiac disease
knowcran discover "celiac disease" --limit 50

# Search with expansion (references, citations, recommendations)
knowcran discover "celiac disease" --limit 50 --expand

# Extract claims from papers matching a topic
knowcran read-topic "celiac disease" --limit 20

# Export Obsidian vault notes
knowcran export-obsidian "celiac disease"

# Generate a literature review
knowcran review "celiac disease" --max-papers 20

# Show database statistics
knowcran stats

# Show a specific paper
knowcran show-paper PAPER_ID
```

## Data Directory Structure

```
data/
  knowcran.sqlite          # SQLite database
  raw/semantic_scholar/    # Cached API responses (SHA-256 keyed)
vault/
  papers/                  # Paper notes with frontmatter
  claims/                  # Individual claim notes
  topics/                  # Topic index notes
  reviews/                 # Literature reviews, evidence matrices, BibTeX
  templates/               # Obsidian templates
```

## Obsidian Vault Usage

Each paper gets a note with YAML frontmatter (paper_id, year, venue, tags) and sections for abstract, key claims, methods, limitations, and open questions. Claim notes link back to their source paper. Topic notes aggregate papers and evidence.

## Current Limitations

- **Abstract-only reading**: Claims are extracted from abstracts only. Full-text PDF ingestion is not yet supported. Abstract-only reading may miss study limitations and full methods.
- **Semantic Scholar rate limits**: 1 req/sec with API key, lower without. Large searches take time. API client is rate-limited and cached.
- **No LLM extraction**: v1 uses deterministic sentence matching for claim extraction.
- **Review output quality**: The current review output is an evidence digest, not a polished narrative review. Review output is traceable but not yet high-quality academic prose.
- **Metadata completeness**: Semantic Scholar metadata can be incomplete. PubMed, Crossref, and OpenAlex should be added later for metadata repair.

## Next Steps

- PDF full-text ingestion
- LLM-powered claim extraction
- Vector index for semantic search
- Robin-like hypothesis ranking
