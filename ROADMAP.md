# Roadmap

This roadmap tracks what should happen after the 1.0.0 production baseline.

## 1.0.x Stabilization

- Keep CI green across Linux, macOS, and Windows.
- Improve MCP protocol smoke tests for real stdio handshakes.
- Harden path validation tests for Windows drive boundaries and symlink escapes.
- Improve migration tests for databases created by earlier local versions.
- Publish signed GitHub releases with source distributions and wheels.

## 1.1 PDF Knowledge Base (Completed)

- PDF downloading from 12 sources with multi-source racing.
- PDF parsing into page-aware text chunks with PyMuPDF.
- Full-text claim extraction with provenance tracking.
- SQLite FTS5 full-text search across parsed PDFs.
- Structured paper notes linked to claims and chunks.
- Robin-style topic run pipeline.
- Full-text review generation prioritizing full-text evidence.
- MCP tools for fulltext search, PDF status, and evidence context.

## 1.2 Evidence Quality

- Upgrade answer audit from citation-pattern checks to sentence-level claim matching.
- Add stronger overclaim detection for causality, animal-to-human extrapolation, and abstract-only evidence.
- Add configurable compact, standard, and full response detail modes for MCP tools.
- Add evidence coverage summaries by year, evidence type, and study type.

## 1.3 Metadata Repair

- Add Crossref, PubMed, or OpenAlex metadata repair as admin-only workflows.
- Add DOI, PMID, and arXiv import workflows.
- Improve BibTeX escaping and duplicate citation-key resolution.

## 1.4 OCR and Vector Search

- Add OCR adapter for scanned PDFs.
- Add vector embeddings for semantic search.
- Implement hybrid keyword + vector search with reranking.

## Not In Scope

- Hosted multi-tenant service.
- Autonomous database mutation by remote agents.
- Clinical decision support.
- Claims that generated reviews replace expert literature review.
