# Mnemosyne PDF Knowledge Base Plan

Date: 2026-05-31

## Goal

Upgrade Mnemosyne from an abstract-level literature evidence tool into a local PDF knowledge base. The target system should discover papers, download PDFs, parse full text, create linked notes, build a searchable evidence store, write literature reviews, and expose reliable evidence retrieval to Codex, Antigravity, or other MCP clients.

The plan uses `Future-House/robin` as an architectural reference for structured scientific workflows and output artifacts, but does not depend on Robin's Edison platform APIs. PDF downloading will be implemented by拆解 `scansci-pdf` 的公开 Python fallback 能力 into Mnemosyne.

## Scope

### In Scope

- Vendor or rewrite public Apache-2.0 parts of `scansci-pdf`.
- Default PDF download strategy: full-source mode with Sci-Hub and LibGen enabled.
- Fixed PDF storage directory: `data/pdfs`.
- DOI/arXiv-based PDF download.
- Batch download by topic.
- PDF status tracking in SQLite.
- PDF parsing into page-aware text chunks.
- Full-text claim extraction.
- Reading notes linked to PDF chunks and claims.
- Local SQLite full-text search.
- Obsidian-style export.
- Robin-style structured output directories.
- Literature review generation with citations and evidence provenance.
- MCP tools for Codex / Antigravity evidence retrieval.

### Out Of Scope

- Reverse engineering `scansci-pdf` proprietary `_core/*.pyd` / `_core/*.so`.
- Reconstructing proprietary `_core/*.pyx` source code.
- Cloud multi-user deployment.
- Browser UI.
- Clinical decision support.
- First-pass OCR for scanned PDFs.

## Guiding Constraints

- Only migrate code that is publicly available under a compatible license.
- Do not depend on `scansci_pdf._core`; use pure Python fallback logic.
- Preserve Mnemosyne's local-first design.
- Keep abstract-only workflows working as fallback.
- Every full-text claim must preserve provenance: `paper_id`, `asset_id`, `chunk_id`, page number, quote, and citation key.
- Full-source downloading is enabled by default per project decision, but documentation must clearly describe compliance risk.

## Target Architecture

### 1. Discovery Layer

Existing Mnemosyne discovery stays in place:

- Semantic Scholar search.
- Paper metadata storage.
- DOI / PMID / arXiv ID collection.
- `openAccessPdf` metadata capture.

Future enhancement:

- Add OpenAlex search as a secondary source.
- Use DOI/title resolution for papers with incomplete metadata.

### 2. PDF Fetch Layer

Create a new Mnemosyne subsystem:

```text
knowcran/paper_fetch/
  __init__.py
  identifiers.py
  downloader.py
  pdf_utils.py
  cache.py
  config.py
  sources/
    __init__.py
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
```

This layer handles:

- DOI normalization.
- arXiv ID detection.
- PDF URL discovery.
- Multi-source download racing.
- PDF validation.
- File naming.
- Download result schema.
- Source scoring.
- Batch download progress.

### 3. PDF Parse Layer

Create:

```text
knowcran/pdf_parse.py
```

First implementation:

- Use `PyMuPDF` for text extraction.
- Extract page text.
- Split into chunks.
- Preserve page numbers.
- Detect empty/scanned PDFs.
- Store chunks in SQLite.

Future implementation:

- OCR adapter for scanned PDFs.
- Table extraction.
- Figure caption extraction.
- Better section detection.

### 4. Knowledge Store Layer

Extend SQLite with:

- `paper_assets`
- `paper_fulltext_chunks`
- `paper_notes`
- `review_runs`

The database becomes the main local knowledge base.

### 5. Review And Reasoning Layer

Extend current `reading.py` and `review.py`:

- Abstract-only extraction remains available.
- Full-text extraction becomes available when PDF chunks exist.
- Review generation prefers full-text claims.
- Every review statement must be backed by claim/chunk provenance.

### 6. Agent Access Layer

Expose new CLI and MCP tools:

- Download PDFs.
- Parse PDFs.
- Search full text.
- Retrieve evidence context.
- Generate topic review artifacts.
- Export notes and references.

## Phase 0: Baseline Audit

- Record current Mnemosyne behavior: `discover`, `read-topic`, `review`, `export-obsidian`, MCP profiles.
- Mark current limitation: abstract-only evidence.
- Audit `scansci-pdf` public source tree.
- Identify modules that can be safely migrated.
- Identify modules that need to be rewritten.
- Confirm license attribution requirements.
- Add a migration note explaining that proprietary `_core` modules are excluded.

## Phase 1: Dependencies And Configuration

Update `pyproject.toml`:

- Add PDF/download dependencies:
  - `requests`
  - `beautifulsoup4`
  - `pymupdf`
  - optionally `lxml`
- Keep heavier browser/Tor dependencies optional.

Add config in `knowcran/config.py`:

```text
MNEMOSYNE_PDF_DOWNLOAD_ENABLED=true
MNEMOSYNE_PDF_DIR=data/pdfs
MNEMOSYNE_PDF_STRATEGY=fastest
MNEMOSYNE_SCIHUB_ENABLED=true
MNEMOSYNE_LIBGEN_ENABLED=true
MNEMOSYNE_TOR_ENABLED=false
MNEMOSYNE_PDF_BATCH_WORKERS=5
```

Rules:

- Default PDF directory is fixed at `data/pdfs`.
- Files outside configured data root are rejected.
- PDF downloads are never committed.
- Source strategy defaults to `fastest`.
- Sci-Hub and LibGen are enabled by default.

## Phase 2: Database Schema

Add `paper_assets`:

```sql
CREATE TABLE IF NOT EXISTS paper_assets (
    asset_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    doi TEXT,
    arxiv_id TEXT,
    file_path TEXT,
    source TEXT,
    strategy TEXT,
    status TEXT NOT NULL,
    error TEXT,
    sha256 TEXT,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Add `paper_fulltext_chunks`:

```sql
CREATE TABLE IF NOT EXISTS paper_fulltext_chunks (
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

Add `paper_notes`:

```sql
CREATE TABLE IF NOT EXISTS paper_notes (
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

Add or extend `review_runs`:

- `run_id`
- `topic`
- `input_papers_json`
- `input_claims_json`
- `input_chunks_json`
- `output_dir`
- `status`
- `created_at`

Indexes:

- `idx_paper_assets_paper_id`
- `idx_fulltext_chunks_paper_id`
- SQLite FTS5 table for chunk text.

## Phase 3: Vendor scansci-pdf Public Downloader

Do not copy private `_core`.

Migrate or rewrite:

- DOI normalization.
- arXiv handling.
- PDF validation.
- Download result helpers.
- Source selection.
- Source racing.
- Batch progress.
- Cache lookup.
- Source scoring.

Source behavior:

- Every source returns a common result object:

```json
{
  "success": true,
  "identifier": "10.xxxx/example",
  "doi": "10.xxxx/example",
  "source": "Sci-Hub",
  "file": "data/pdfs/example.pdf",
  "error": null
}
```

Strategies:

- `fastest`: all sources race in parallel.
- `oa_first`: open access sources first, grey sources fallback.
- `legal_only`: arXiv, PMC, Unpaywall, OpenAlex, Semantic Scholar, publisher direct, institutional sources.
- `scihub_only`: Sci-Hub only.

Default:

```text
fastest
```

## Phase 4: Mnemosyne Fulltext API

Create:

```text
knowcran/fulltext.py
```

Core functions:

```python
download_paper_pdf(paper_id: str, strategy: str = "fastest") -> dict
download_topic_pdfs(topic: str, limit: int = 20, strategy: str = "fastest") -> dict
get_pdf_status(topic: str | None = None, paper_id: str | None = None) -> dict
parse_paper_pdf(paper_id: str) -> dict
parse_topic_pdfs(topic: str, limit: int = 20) -> dict
```

Download resolution order:

1. DOI.
2. arXiv ID.
3. `open_access_pdf_json`.
4. Paper URL.

Behavior:

- Skip if valid PDF already exists.
- Re-download only with `force=True`.
- Store every attempt in `paper_assets`.
- Return structured success/failure details.

## Phase 5: CLI Integration

Add commands:

```bash
knowcran download-paper PAPER_ID
knowcran download-topic TOPIC --limit 20 --strategy fastest
knowcran pdf-status TOPIC
knowcran parse-paper PAPER_ID
knowcran parse-topic TOPIC --limit 20
knowcran read-fulltext PAPER_ID --topic TOPIC
knowcran review-fulltext TOPIC --max-papers 30
knowcran run-topic TOPIC --limit 50
```

Keep existing commands:

```bash
knowcran discover
knowcran read-paper
knowcran read-topic
knowcran review
knowcran export-obsidian
```

Enhance:

- `read-paper --fulltext`
- `read-topic --fulltext`
- `review --fulltext`

Fallback:

- If no PDF exists, use abstract-only mode and warn clearly.

## Phase 6: PDF Parsing

Use `PyMuPDF` first.

Parser responsibilities:

- Open PDF safely.
- Reject invalid PDF files.
- Extract text per page.
- Detect empty pages.
- Combine page text into chunks.
- Store chunks with page references.
- Compute text hashes for idempotency.

Chunking rules:

- Target 800-1500 words per chunk.
- Preserve page boundaries when possible.
- Store page start and page end.
- Try to identify section labels:
  - Abstract
  - Introduction
  - Methods
  - Results
  - Discussion
  - Conclusion
  - References

Risk handling:

- If no text is extracted, set parse status to `needs_ocr`.
- If PDF is encrypted, set status to `encrypted`.
- If parser fails, preserve error and continue batch run.

## Phase 7: Full-text Claim Extraction

Extend extraction to use PDF chunks.

New evidence statuses:

- `metadata_only`
- `abstract_only`
- `full_text_reviewed`
- `direct_evidence`

New source fields:

- `source_quote`
- `source_span_json`
- `chunk_id`
- `page_start`
- `page_end`

Workflow:

1. Select relevant chunks by topic keywords or FTS search.
2. Extract methods/results/limitations/open questions.
3. Store claims with chunk provenance.
4. Avoid duplicates by claim hash + chunk hash.

Fallback:

- If no full text chunks exist, use existing abstract extraction.

## Phase 8: Notes And Links

Generate structured paper notes:

```markdown
# Paper Title

## Metadata

## PDF

## Research Question

## Methods

## Key Results

## Limitations

## Evidence Quotes

## Claims

## Links
```

Link types:

- Paper to PDF asset.
- Claim to chunk.
- Claim to source quote.
- Paper to topic.
- Topic to review.
- Review to claims.

Obsidian export:

- `vault/papers/`
- `vault/claims/`
- `vault/topics/`
- `vault/reviews/`
- `vault/pdfs/` or links to `data/pdfs`

## Phase 9: Local Knowledge Retrieval

Add full-text search:

```bash
knowcran search-fulltext "hematoma expansion" --topic "intracerebral hemorrhage"
```

Implement:

- SQLite FTS5 on chunks.
- Topic-scoped search.
- Paper-scoped search.
- Evidence-type scoped search.
- Citation-key lookup.

Return:

- Paper title.
- Year.
- Citation key.
- Chunk text.
- Page range.
- Claim IDs.
- Evidence status.

Future:

- Vector embeddings.
- Hybrid keyword + vector search.
- Reranking.

## Phase 10: Robin-style Workflow Layer

Robin's useful pattern is not PDF parsing itself, but the structured scientific workflow and output directory.

Add Mnemosyne run output:

```text
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

Add `ResearchRun` model:

- `run_id`
- `topic`
- `created_at`
- `query_plan`
- `paper_count`
- `pdf_count`
- `parsed_count`
- `claim_count`
- `review_paths`
- `status`

Add command:

```bash
knowcran run-topic "intracerebral hemorrhage" --limit 50
```

Pipeline:

1. Discover papers.
2. Download PDFs.
3. Parse PDFs.
4. Extract full-text claims.
5. Generate paper notes.
6. Generate evidence matrix.
7. Generate literature review.
8. Export bibliography.
9. Write run manifest.

## Phase 11: Review Generation

Add:

```bash
knowcran review-fulltext TOPIC --max-papers 30
```

Review sections:

- Background.
- Search and evidence coverage.
- Key findings.
- Mechanisms.
- Clinical relevance.
- Contradictions.
- Limitations.
- Open questions.
- References.

Hard rules:

- Every strong claim must cite stored evidence.
- Prefer full-text reviewed claims.
- Mark abstract-only evidence explicitly.
- Do not convert animal model evidence into clinical proof.
- Do not cite unavailable papers.
- Do not invent references.

Outputs:

- `literature_review.md`
- `evidence_matrix.csv`
- `open_questions.md`
- `bibliography.bib`

## Phase 12: MCP And Agent Access

Add readonly MCP tools:

- `knowcran_search_fulltext`
- `knowcran_get_pdf_status`
- `knowcran_get_paper_note`
- `knowcran_get_evidence_context`
- `knowcran_get_review_artifacts`

Add curate MCP tools:

- `knowcran_download_paper_pdf`
- `knowcran_download_topic_pdfs`
- `knowcran_parse_paper_pdf`
- `knowcran_parse_topic_pdfs`
- `knowcran_read_fulltext`
- `knowcran_review_fulltext`
- `knowcran_run_topic`

Profile rules:

- readonly: no downloads, no parsing, no writes.
- curate: download, parse, extract, review.
- admin: repair, dedupe, reindex.

Agent use cases:

- Codex asks: "Find reliable evidence for X."
- Mnemosyne returns chunks + claims + citation keys.
- Codex writes answer with references.
- Antigravity can call the same MCP tools.

## Phase 13: Testing

Unit tests:

- DOI normalization.
- arXiv ID detection.
- PDF validation.
- Safe filename.
- Source result schema.
- `paper_assets` migration.
- Chunk hashing.
- FTS search.

Mocked downloader tests:

- Source success.
- Source failure.
- First source wins race.
- Duplicate DOI skipped.
- Existing PDF cache hit.
- Batch resume.

Integration tests:

- Create paper metadata.
- Use fake PDF.
- Register asset.
- Parse PDF.
- Store chunks.
- Extract claim.
- Generate note.
- Generate review artifact.

MCP tests:

- readonly cannot download.
- curate can download.
- readonly can search full text.
- tool schemas expose required fields.

Regression tests:

- Existing abstract-only tests still pass.
- `read-topic` works without PDF.
- `review` works without PDF.
- Topic alias behavior does not regress.

Windows tests:

- `data/pdfs` path handling.
- Illegal filename characters.
- Long path handling.
- Path traversal rejection.

## Phase 14: Documentation

Update README:

- Add "PDF Knowledge Base" section.
- Add full workflow quick start.
- Add warning about full-source mode.
- Explain `data/pdfs`.
- Explain abstract-only fallback.

Update SECURITY:

- Downloaded PDF risks.
- Path restrictions.
- Cookie/API key risks.
- Sci-Hub/LibGen compliance warning.
- No PDF execution.

Update ROADMAP:

- 1.1 PDF downloader.
- 1.2 PDF parser.
- 1.3 local full-text knowledge base.
- 1.4 full-text review generation.
- 1.5 OCR and vector search.

Add docs:

- `docs/fulltext.md`
- `docs/pdf-download-sources.md`
- `docs/mcp/fulltext-tools.md`
- `docs/agent-workflows.md`

## Phase 15: Rollout

Milestone 1:

- PDF downloader.
- `paper_assets`.
- `download-paper`.
- `download-topic`.
- `pdf-status`.

Milestone 2:

- PDF parser.
- `paper_fulltext_chunks`.
- `parse-paper`.
- `parse-topic`.
- FTS search.

Milestone 3:

- Full-text claim extraction.
- Linked notes.
- Obsidian export improvements.

Milestone 4:

- Robin-style topic runs.
- Full-text review artifacts.
- Run manifest.

Milestone 5:

- MCP tools for Codex / Antigravity.
- Reliable evidence retrieval.
- Reference-backed answer generation.

## Risks

### Compliance Risk

Default Sci-Hub/LibGen support increases PDF access success but creates legal and institutional compliance risk. Documentation must be explicit.

### Maintenance Risk

Source-specific download logic can break when websites change.

### Parsing Risk

PDF extraction quality varies with layout, scanned pages, tables, equations, and publisher formatting.

### Evidence Risk

LLM review generation can overclaim. Every generated claim must be tied to stored evidence.

### Performance Risk

Large PDF collections need batching, resume, skip-existing, and indexing controls.

### Windows Risk

File paths, long names, subprocess behavior, and encoding need dedicated tests.

## Validation Commands

```bash
pytest -v
pytest tests/test_pdf_fetch.py -v
pytest tests/test_fulltext.py -v
pytest tests/test_mcp_server.py -v
python -m compileall knowcran tests
knowcran download-paper <paper_id> --strategy fastest
knowcran parse-paper <paper_id>
knowcran search-fulltext "hematoma expansion"
knowcran review-fulltext "intracerebral hemorrhage" --max-papers 10
```

## Final Target

Mnemosyne should become a local scientific knowledge base that can:

1. Search and store literature metadata.
2. Download PDFs into `data/pdfs`.
3. Parse full text into page-aware chunks.
4. Extract traceable claims.
5. Generate linked notes.
6. Build evidence matrices.
7. Write literature reviews.
8. Export Obsidian-compatible notes.
9. Serve reliable evidence through MCP.
10. Let Codex or Antigravity generate reference-backed writing from the local knowledge base.

