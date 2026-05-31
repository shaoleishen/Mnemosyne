# Full-Text Knowledge Base

This document describes Mnemosyne's full-text PDF knowledge base capabilities.

## Overview

Mnemosyne 1.1.0 adds the ability to download PDFs, parse them into page-aware text chunks, and extract claims with full provenance (page, section, chunk ID, source quote).

## Architecture

```
paper_fetch/          # PDF download subsystem
  identifiers.py      # DOI normalization, arXiv ID detection
  downloader.py       # Multi-source download orchestrator
  pdf_utils.py        # PDF validation, filename generation
  cache.py            # Filesystem cache
  config.py           # Source configuration and strategies
  sources/            # 12 download sources
    arxiv.py
    unpaywall.py
    openalex.py
    semantic_scholar.py
    europepmc.py
    pmc.py
    core.py
    doaj.py
    crossref.py
    publishers.py
    libgen.py
    scihub.py

pdf_parse.py          # PyMuPDF-based PDF parser
fulltext.py           # High-level API (download, parse, search)
notes.py              # Structured paper notes
workflow.py           # Robin-style topic run pipeline
```

## Download Strategies

| Strategy | Description |
| --- | --- |
| `fastest` | All sources race in parallel. Default. |
| `oa_first` | Open access sources first, grey sources as fallback. |
| `legal_only` | Only legal/open access sources (no Sci-Hub, no LibGen). |
| `scihub_only` | Sci-Hub only. |

## Database Schema

### paper_assets

Tracks PDF download attempts and results.

```sql
CREATE TABLE paper_assets (
    asset_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'pdf',
    doi TEXT,
    arxiv_id TEXT,
    file_path TEXT,
    source TEXT,
    strategy TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    sha256 TEXT,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### paper_fulltext_chunks

Stores parsed text chunks with page references.

```sql
CREATE TABLE paper_fulltext_chunks (
    chunk_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    section TEXT,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    text_hash TEXT,
    token_count INTEGER,
    created_at TEXT NOT NULL
);
```

### paper_notes

Structured paper notes linked to claims and chunks.

```sql
CREATE TABLE paper_notes (
    note_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    topic TEXT,
    note_type TEXT,
    title TEXT,
    body TEXT,
    linked_claim_ids_json TEXT,
    linked_chunk_ids_json TEXT,
    created_at TEXT NOT NULL
);
```

## Evidence Status

Claims now have an `evidence_status` field:

| Status | Description |
| --- | --- |
| `metadata_only` | Only paper metadata available. |
| `abstract_only` | Claim extracted from abstract only. |
| `full_text_reviewed` | Claim extracted from full text with provenance. |
| `direct_evidence` | Direct quote from full text with page reference. |

## Chunking Rules

- Target 800-1500 words per chunk.
- Preserve page boundaries when possible.
- Store page start and page end.
- Detect section labels: Abstract, Introduction, Methods, Results, Discussion, Conclusion, References.

## Full-Text Search

SQLite FTS5 provides full-text search across all parsed chunks:

```bash
knowcran search-fulltext "hematoma expansion" --topic "intracerebral hemorrhage"
```

## Topic Pipeline

The `run-topic` command runs the complete pipeline:

1. Discover papers
2. Download PDFs
3. Parse PDFs
4. Extract full-text claims
5. Generate paper notes
6. Generate evidence matrix
7. Generate literature review
8. Export bibliography
9. Write run manifest

```bash
knowcran run-topic "intracerebral hemorrhage" --limit 50
```

Output directory structure:

```
mnemosyne_output/
  <topic_slug>_<timestamp>/
    run_manifest.json
    topic_summary.md
    paper_inventory.csv
    pdf_status.csv
    evidence_matrix.csv
    literature_review.md
    open_questions.md
    bibliography.bib
    paper_notes/
      <citation_key>.md
    extracted_claims/
      claims.json
```
