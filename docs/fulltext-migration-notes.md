# Full-Text Knowledge Base Migration Notes

Date: 2026-05-31

## Current Baseline (v1.0.0)

Mnemosyne v1.0.0 is an abstract-level evidence tool:

- Discovery via Semantic Scholar API
- Claim extraction from paper abstracts only (deterministic regex + optional LLM/agent)
- Review generation from abstract-level claims
- Obsidian vault export
- MCP server with readonly/curate/admin profiles

**Limitation**: All evidence is derived from abstracts. No access to full text, methods sections, results tables, or discussion details.

## scansci-pdf Audit

### What We Migrate (Public Apache-2.0 / Pure Python)

- DOI normalization logic
- arXiv ID detection and handling
- PDF validation (magic bytes, size checks)
- Download result schema pattern
- Source selection and racing strategy
- Batch progress tracking pattern
- Cache lookup pattern
- Source scoring heuristics

### What We Do NOT Migrate

- `scansci_pdf._core/*.pyd` / `_core/*.so` (proprietary compiled modules)
- `scansci_pdf._core/*.pyx` (proprietary Cython source)
- Any code that imports from `_core`
- Proprietary browser automation / cookie harvesting

### License Attribution

All vendored or rewritten code carries Apache-2.0 attribution headers referencing both Mnemosyne and the original scansci-pdf project where applicable.

## Sci-Hub / LibGen Compliance Warning

Full-source downloading is enabled by default per project decision. This means:

- PDF downloads may use Sci-Hub, LibGen, or similar grey sources
- These sources may not comply with publisher terms of service
- Users in jurisdictions with strict copyright enforcement should set `MNEMOSYNE_PDF_STRATEGY=legal_only`
- Institutional users should consult their library's policies before enabling default mode
- Documentation must clearly describe compliance risk at every entry point

## Abstract-Only Fallback

All existing abstract-only workflows continue to function. When no PDF is available:

- `read-paper` / `read-topic` use abstract extraction (unchanged)
- `review` uses abstract-level claims (unchanged)
- CLI warns clearly when falling back to abstract-only mode
- MCP tools report evidence status accurately

## Architecture Decisions

1. **Package structure**: New `knowcran/paper_fetch/` module for download logic
2. **PDF storage**: Fixed `data/pdfs/` directory, never committed to git
3. **Database**: New tables for assets, chunks, notes; FTS5 for full-text search
4. **Parsing**: PyMuPDF first, OCR adapter as future enhancement
5. **Source strategy**: `fastest` (all sources race in parallel) as default
