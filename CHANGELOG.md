# Changelog

All notable changes to Mnemosyne / KnowCran are documented here.

## 1.1.0 - 2026-06-14

### Added

- Multi-modal Obsidian vault note rendering: exports inline figures and tables in paper notes using relative image paths and visual VLM interpretation callouts.
- Configurable MinerU parser timeout parameter (`MNEMOSYNE_MINERU_TIMEOUT_SECONDS`) to support parsing large/complex academic PDFs.
- Resilient OpenAI-compatible Vision API/VLM routing failovers, dynamically marking failed providers unhealthy and falling back to backup providers.
- Data URL Base64 encoding for local figures/tables during multimodal RAG prompt generation, replacing absolute file:// paths.
- Soft cap for review synthesis: limits review referencing to a maximum of 100 papers to prevent LLM context overflows.
- Clean cascade delete in SQLite storage for media assets, VLM descriptions, and mentions during paper re-parsing.

### Fixed

- Rerank scoring dictionary parser KeyErrors in `discovery.py` when LLM rerank results are empty or malformed.

## 1.0.0 - 2026-05-31

### Added

- Formal 1.0.0 project metadata and release documentation.
- Apache-2.0 license file.
- Production README with installation, MCP profile, evidence contract, testing, and limitation sections.
- Contributor guide, roadmap, and 1.0.0 release checklist.
- Cross-platform CI matrix for Linux, macOS, and Windows on Python 3.12 and 3.13.
- Static metadata regression tests for version consistency and required release artifacts.
- Managed local service layer for MinerU and OpenAI-compatible local embeddings.
- Tag-triggered GitHub Release and PyPI Trusted Publishing workflow.
- Declared `requests` and `beautifulsoup4` as core dependencies for the PDF source downloaders.
- README feature scope now reflects the implemented local PDF parsing, FTS5 indexing, hybrid search, and managed-service workflow.
- Full-text compliance notes document for legal-only source strategies and Sci-Hub/LibGen configuration.

### Changed

- Project version is now `1.0.0` in `pyproject.toml` and `knowcran.__version__`.
- Project status is now a production release candidate rather than alpha.
- PyPI development classifier now matches release-candidate status until the full release gate has passed.
- CI now includes package build verification.
- Legacy CI workflow now mirrors key smoke checks for CLI doctor, test compilation, MCP startup, and local service probe imports.
- Local service health checks now probe real service health endpoints instead of treating HTTP 404/405 as healthy.
- PDF download and parse concurrency now respect configured worker limits.
- `MNEMOSYNE_PDF_DOWNLOAD_ENABLED=false` now disables PDF downloads instead of being documentation-only.
- MCP full-text handlers now pass checked `data_dir`/`vault_dir` through `Settings`, so worker threads use the requested local database instead of the default path.
- Roadmap now treats full-text support as a 1.0 baseline capability with post-1.0 quality hardening, not a future-only feature.
- Managed MinerU and local embedding startup timeouts are configurable for first-run model loading.
- Re-parsing a paper now replaces stale parsed pages, chunks, legacy chunks, and embeddings instead of accumulating duplicate searchable content.
- PDF cache filenames now use DOI first, then arXiv ID, then a safe title/fallback basename.
- MCP evidence-context lookup now uses the claim primary key directly and returns paper/chunk/PDF asset context.
- Workflow output directories now use the shared safe slugifier for topic names.
- MCP `knowcran_run_topic` now exposes the same fulltext and skip-step controls as the CLI workflow.

### Notes

- Cloud multi-tenancy and polished narrative review generation remain outside the 1.0.0 scope.
- Semantic Scholar remains the primary discovery source.
- LLM and agent providers remain optional; deterministic mode is still supported.
