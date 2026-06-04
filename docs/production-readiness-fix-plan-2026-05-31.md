# Mnemosyne Production Readiness Fix Plan

Date: 2026-05-31

> This document is a historical implementation/audit plan. The current 1.0.0
> release-candidate README, release checklist, and changelog are authoritative
> for the present release scope.

This plan upgrades the current Mnemosyne / KnowCran 1.1.0 PDF knowledge-base implementation from a prototype into a production-usable local research system. The immediate goal is to make the advertised full-text workflow actually work end to end: discover papers, download PDFs, parse them, extract full-text claims with provenance, search the local full text, generate notes and reviews, and expose reliable read tools to Codex or other MCP clients.

## Scope

### In Scope

- Fix PDF downloading so successful source downloads are persisted instead of being reported as failed.
- Align CLI and README commands with the implemented Python APIs.
- Make `run-topic` a real end-to-end workflow.
- Make full-text parsing, FTS indexing, full-text claim extraction, paper notes, review artifacts, and MCP tools reliable.
- Add production-grade tests, CI gates, smoke tests, and release checks.
- Add safety controls for grey sources such as Sci-Hub and LibGen while preserving the requested default behavior.

### Out Of Scope

- Reverse engineering proprietary `scansci-pdf` `_core/*.pyx` binaries.
- Building OCR for scanned PDFs in the first production pass.
- Depending on Future-House Robin or Edison APIs at runtime.
- Guaranteeing access to paywalled publisher content beyond user-configured source availability.
- Replacing expert literature review with automated review generation.

## Production Readiness Definition

Mnemosyne is production-usable when all of the following are true:

- A new user can follow README commands without hitting missing CLI options.
- `knowcran run-topic "<topic>" --limit N` can complete a realistic local run from discovery through review artifacts.
- At least one legal direct PDF source path works in mocked tests and live smoke tests.
- Full-text claims include `paper_id`, `claim_id`, `source_location`, `evidence_status`, and source span metadata when extracted from PDF chunks.
- FTS search returns stable results after repeated parse/index operations.
- MCP readonly mode exposes only non-mutating tools, and curate/admin modes are clearly separated.
- CI passes on Windows, Linux, and macOS for supported Python versions.
- Failures are explicit and actionable rather than silently swallowed.

## Current Blocking Findings

### P0: PDF Downloads Fail Even When A Source Succeeds

Files:

- `knowcran/paper_fetch/downloader.py`
- `knowcran/fulltext.py`
- `tests/test_pdf_fetch.py`

Problem:

- `DownloadResult` is a dataclass without an `_data` field.
- `_try_source()` constructs `DownloadResult(..., _data=data)`.
- This raises `TypeError`, is swallowed by the broad `except`, and causes all sources to appear failed.

Required fix:

- Add a private/non-serialized payload field to `DownloadResult`, for example `data: bytes | None = field(default=None, repr=False, compare=False)`.
- Use that field consistently in `_race_sources()` and `_sequential_sources()`.
- Do not leak PDF bytes through `to_dict()`.
- Add tests proving a mocked source that returns valid PDF bytes is stored in `data/pdfs`.

Acceptance:

- `download_pdf(arxiv_id="2301.12345", strategy="legal_only")` succeeds in a mocked source test.
- `DownloadResult.to_dict()` never includes raw bytes.
- Failed source exceptions are logged with enough context.

### P0: README Commands Do Not Match CLI

Files:

- `README.md`
- `knowcran/cli.py`
- `knowcran/reading.py`
- `knowcran/review.py`
- `tests/test_cli.py`

Problem:

- README advertises:
  - `knowcran read-topic ... --fulltext`
  - `knowcran review ... --fulltext`
- CLI does not define `--fulltext` for `read-topic`, `read-paper`, or `review`.

Required fix:

- Add `fulltext: bool = typer.Option(False, "--fulltext", help="Use parsed PDF chunks when available")` to:
  - `read-paper`
  - `read-topic`
  - `review`
- Pass the flag into `read_paper(..., fulltext=fulltext)`, `read_topic(..., fulltext=fulltext)`, and `review(..., fulltext=fulltext)`.
- Update help text so abstract fallback is explicit.

Acceptance:

- `knowcran read-topic "topic" --fulltext --help` shows the option.
- `knowcran review "topic" --fulltext --help` shows the option.
- CLI tests fail if README examples drift from implemented commands.

### P0: `run-topic` Is Not An End-To-End Pipeline

Files:

- `knowcran/cli.py`
- `knowcran/workflow.py`
- `knowcran/discovery.py`
- `knowcran/fulltext.py`
- `knowcran/reading.py`
- `knowcran/review.py`
- `tests/test_workflow.py`

Problem:

- CLI docstring says `discover -> download -> parse -> extract -> notes -> review`.
- Actual CLI requires papers to already exist and never runs full-text extraction.
- `workflow.py` creates some structured outputs but does not generate the final review artifacts expected by README.

Required fix:

- Consolidate pipeline logic in `knowcran/workflow.py`.
- Make CLI `run-topic` call `run_topic_workflow()` instead of duplicating partial logic.
- Add workflow options:
  - `--skip-discover`
  - `--skip-download`
  - `--skip-parse`
  - `--skip-review`
  - `--fulltext/--abstract-only`
  - `--strategy`
- Default pipeline:
  1. Resolve canonical topic.
  2. Discover papers if topic has insufficient local papers.
  3. Download PDFs.
  4. Parse PDFs.
  5. Run `read_topic(..., fulltext=True)`.
  6. Generate paper notes linked to claims and chunks.
  7. Generate full-text review.
  8. Write Robin-style run directory.
  9. Record run manifest and DB review run.

Acceptance:

- One workflow function is used by CLI and MCP.
- `run-topic` produces:
  - `run_manifest.json`
  - `paper_inventory.csv`
  - `pdf_status.csv`
  - `evidence_matrix.csv`
  - `topic_summary.md`
  - review markdown
  - bibliography
  - open questions
- The run manifest records which steps were skipped, failed, or completed.

## Phase 1: Repair PDF Download Subsystem

### 1.1 Fix DownloadResult Payload Handling

Tasks:

- Add an internal bytes field to `DownloadResult`.
- Replace every `result._data` access with the new field.
- Ensure cache hits return metadata without requiring bytes.
- Make source failures distinguish:
  - no identifier
  - HTTP failure
  - invalid PDF
  - timeout
  - source exception
  - all sources failed

Tests:

- Unit test with mocked arXiv source returning valid PDF.
- Unit test with invalid PDF bytes.
- Unit test with one failing source and one succeeding source.
- Unit test that cache hit returns without calling sources.

### 1.2 Add Direct URL / OpenAccessPdf Source

Tasks:

- Add `DirectPdfSource` or `OpenAccessPdfSource`.
- Pass `open_access_pdf_json.url` from `download_paper_pdf()` to `download_pdf()`.
- Prefer direct OA URL before grey sources.
- Validate content type and PDF magic.
- Preserve final redirected URL in asset metadata when available.

Tests:

- Paper with only `openAccessPdf.url` downloads successfully.
- Paper with DOI and OA URL chooses OA URL before Sci-Hub/LibGen under `fastest` or `oa_first`.

### 1.3 Make Source Configuration Honest

Tasks:

- Audit all 12 advertised sources.
- Mark sources as `implemented`, `stub`, or `experimental`.
- If CORE requires an API key, make that explicit.
- Add per-source timeout and error reporting.
- Do not claim production support for sources without tests.

Acceptance:

- README source table reflects real implementation status.
- `legal_only` never calls Sci-Hub or LibGen.
- `scihub_only` only calls Sci-Hub.

## Phase 2: Make Full-Text Parsing And FTS Reliable

### 2.1 Fix FTS Rebuild Idempotency

Files:

- `knowcran/storage.py`

Tasks:

- Replace current append-only `sync_chunk_fts()` behavior.
- Either:
  - use `INSERT INTO paper_chunks_fts(paper_chunks_fts) VALUES('rebuild')`, or
  - delete and rebuild the FTS table safely, or
  - create triggers for insert/update/delete on `paper_fulltext_chunks`.
- Add a dedicated `rebuild_fulltext_index()` command if useful.
- Make parse fail loudly or mark index status if FTS sync fails.

Tests:

- Insert chunks, sync, search.
- Sync again, search result count stays stable.
- Parse two papers sequentially, both are searchable.
- Rebuild index after deleting chunks.

### 2.2 Improve PDF Chunk Metadata

Files:

- `knowcran/pdf_parse.py`

Tasks:

- Track section at chunk start, not just latest detected section.
- Fix first non-empty page handling so `page_start` is accurate.
- Split oversized single pages.
- Store `text_hash` deterministically.
- Preserve page range for every chunk.

Tests:

- Empty front matter pages do not shift page numbers.
- Section change on a new page does not relabel previous chunk.
- Long single-page text splits into multiple chunks.

### 2.3 Handle Scanned And Encrypted PDFs Explicitly

Tasks:

- Keep OCR out of the first pass, but record `needs_ocr` clearly.
- Store failed parse status in `paper_assets` or a parse ledger.
- Add `pdf-status` output for:
  - downloaded
  - parsed
  - needs_ocr
  - encrypted
  - parse_error

Acceptance:

- User can tell why a PDF cannot be read.
- Scanned PDFs do not masquerade as successful full-text evidence.

## Phase 3: Full-Text Claim Extraction

### 3.1 Expose Full-Text Mode In CLI

Files:

- `knowcran/cli.py`
- `knowcran/reading.py`
- `knowcran/review.py`

Tasks:

- Add CLI `--fulltext` flags.
- Print counts for:
  - full-text claims
  - abstract fallback claims
  - skipped papers without chunks
- Keep deterministic extraction as fallback.

Acceptance:

- `read-topic --fulltext` creates claims with `evidence_status="full_text_reviewed"` when chunks exist.
- Papers without chunks create abstract-only claims and are labeled as such.

### 3.2 Fix Agent Extraction Runtime Issue

Files:

- `knowcran/reading.py`

Tasks:

- Import or inject `Console` before using `console.print()`.
- Add a test that exercises `agent_provider` path with a deterministic fake provider.
- Ensure agent path can support full-text chunks later or explicitly rejects full-text mode.

Acceptance:

- Agent extraction path does not raise `NameError`.

### 3.3 Tighten Evidence Provenance

Tasks:

- Use structured JSON via `json.dumps()` for `source_span_json` instead of string interpolation.
- Include:
  - `chunk_id`
  - `page_start`
  - `page_end`
  - `section`
  - `text_hash`
- Store `source_quote` as a bounded excerpt.
- Avoid malformed JSON when section/title contains quotes.

Tests:

- `source_span_json` parses for every full-text claim.
- `get_evidence_context` can resolve chunk context from every full-text claim.

## Phase 4: Workflow And Robin-Style Outputs

### 4.1 Consolidate Workflow Logic

Files:

- `knowcran/workflow.py`
- `knowcran/cli.py`
- `knowcran/server/mcp.py`

Tasks:

- Move all orchestration into `run_topic_workflow()`.
- Make CLI and MCP call the same workflow.
- Add structured step results:
  - `discover`
  - `download`
  - `parse`
  - `extract`
  - `notes`
  - `review`
  - `artifacts`
- Store each step status and error.

Acceptance:

- CLI and MCP runs produce equivalent output structure.
- Failed steps do not erase partial successful artifacts.

### 4.2 Generate Complete Run Directory

Tasks:

- Use fixed output base `mnemosyne_output/`.
- For each run, write:
  - `run_manifest.json`
  - `paper_inventory.csv`
  - `pdf_status.csv`
  - `fulltext_chunk_inventory.csv`
  - `evidence_matrix.csv`
  - `topic_summary.md`
  - `literature_review.md`
  - `bibliography.bib`
  - `open_questions.md`
  - `paper_notes/`
  - `extracted_claims/`
- Record absolute or workspace-relative paths in DB.

Acceptance:

- A completed run can be inspected without opening SQLite.
- A Codex/Antigravity session can use the run directory as context.

### 4.3 Review Generation Must Prefer Full Text Without Hiding Abstract Fallback

Files:

- `knowcran/review.py`

Tasks:

- In `fulltext=True`, include full-text claims first.
- Include abstract fallback claims in a separate evidence-status section.
- Add coverage summary:
  - papers selected
  - PDFs downloaded
  - PDFs parsed
  - full-text claims
  - abstract-only claims
  - OCR-needed papers
- Avoid dropping all abstract claims if at least one full-text claim exists.

Acceptance:

- Reviews clearly state evidence coverage and limitations.
- Abstract-only papers remain visible but are not presented as full-text reviewed.

## Phase 5: MCP Production Hardening

### 5.1 Keep Readonly Profile Safe

Files:

- `knowcran/server/tools.py`
- `knowcran/server/mcp.py`

Tasks:

- Verify readonly exposes only:
  - search papers
  - search claims
  - search fulltext
  - get evidence matrix
  - get bibliography
  - get PDF status
  - get evidence context
  - get review artifacts
  - audit answer
- Ensure readonly never performs network calls or writes.

Tests:

- Profile tests for allowed/disallowed tool names.
- Attempt write tool in readonly returns explicit error.

### 5.2 Add Evidence Context Tool Quality Gates

Tasks:

- `knowcran_get_evidence_context` should lookup by `claim_id` directly instead of scanning topics only.
- Return paper metadata, chunk metadata, source quote, evidence status, and file path when available.
- Add clear not-found response.

Acceptance:

- Codex can retrieve the exact supporting chunk for a full-text claim.

### 5.3 Add MCP Smoke Test

Tasks:

- Start `serve-mcp-readonly` in CI or a local smoke script.
- List tools.
- Call `knowcran_stats`.
- Call `knowcran_search_fulltext` against a fixture DB.

Acceptance:

- MCP startup does not depend on a live network.

## Phase 6: Storage And Migration Safety

### 6.1 Add Schema Versioning

Files:

- `knowcran/storage.py`

Tasks:

- Introduce a `schema_migrations` or `meta` table.
- Record schema version.
- Make migrations idempotent.
- Add migration tests from:
  - empty DB
  - 1.0 DB
  - partial 1.1 DB

Acceptance:

- Existing user DB upgrades without data loss.

### 6.2 Make Inserts Idempotent Where Needed

Tasks:

- `paper_assets`: avoid unbounded duplicate failed rows for repeated attempts unless useful.
- `paper_fulltext_chunks`: support reparse by asset or paper.
- `paper_notes`: avoid duplicate notes for repeated workflow runs unless versioned.
- `review_runs`: store valid JSON, not `str(len(papers))`.

Acceptance:

- Re-running the same workflow is predictable.
- Duplicate records are intentional and documented.

## Phase 7: Security, Compliance, And Operational Controls

### 7.1 Grey Source Controls

Tasks:

- Keep requested defaults:
  - `MNEMOSYNE_SCIHUB_ENABLED=true`
  - `MNEMOSYNE_LIBGEN_ENABLED=true`
- Add visible warnings in README and `.env.example`.
- Add `--strategy legal_only` docs for safer environments.
- Log which grey source was used.
- Add config override for organizations that need grey sources disabled.

Acceptance:

- Users understand legal/compliance implications.
- Production deployments can disable grey sources with environment variables.

### 7.2 Network Robustness

Tasks:

- Add retries with exponential backoff for transient HTTP failures.
- Add per-source timeout.
- Add request user-agent and rate limiting.
- Avoid unbounded parallelism.
- Record source-level errors.

Acceptance:

- A flaky source does not block the whole workflow indefinitely.

### 7.3 File Safety

Tasks:

- Keep PDF storage under `data/pdfs`.
- Sanitize filenames.
- Prevent path traversal from source metadata.
- Do not overwrite unrelated local files.

Acceptance:

- All downloaded PDFs resolve inside configured PDF directory.

## Phase 8: Test Strategy

### 8.1 Unit Tests

Add or expand tests for:

- DOI and arXiv normalization.
- Direct OA URL downloads.
- Download result byte payload handling.
- Cache lookup.
- Source strategy selection.
- PDF validation.
- PDF chunking and section detection.
- FTS indexing idempotency.
- Full-text claim extraction.
- Review full-text prioritization.
- MCP profile gating.

### 8.2 Integration Tests

Add fixture-based tests:

- Create temp SQLite DB.
- Insert sample paper metadata.
- Mock a PDF download.
- Parse fixture PDF.
- Search full text.
- Extract full-text claims.
- Generate review artifacts.
- Verify output directory contents.

### 8.3 CLI Tests

Use Typer `CliRunner` to verify:

- `knowcran read-topic --fulltext`
- `knowcran read-paper --fulltext`
- `knowcran review --fulltext`
- `knowcran run-topic --skip-discover`
- `knowcran search-fulltext`
- `knowcran pdf-status`

### 8.4 Live Smoke Tests

Keep live network tests optional and off by default:

- `MNEMOSYNE_LIVE_TESTS=1 pytest tests/live/`
- Use one known arXiv paper.
- Use `legal_only`.
- Do not use Sci-Hub/LibGen in CI live tests.

## Phase 9: CI And Release Gates

### 9.1 CI Matrix

Run on:

- Windows
- Linux
- macOS
- Python 3.12
- Python 3.13

Commands:

- `python -m pip install -e ".[dev]"`
- `pytest -q`
- `python -m build`
- `knowcran --help`
- `knowcran serve-mcp-readonly` smoke check if feasible

### 9.2 Quality Gates

Before release:

- All unit and integration tests pass.
- README Quick Start commands are tested or generated from CLI help.
- Wheel builds.
- Fresh install works.
- Existing DB migration test passes.
- No raw PDF bytes appear in serialized outputs.

### 9.3 Release Checklist

- Update version to `1.1.1` or `1.2.0` depending on scope.
- Update CHANGELOG.
- Remove stale README limitation saying full-text ingestion is not part of 1.0.0.
- Add migration notes.
- Add known limitations:
  - no OCR yet
  - PDF availability depends on source access
  - deterministic extraction is conservative

## Phase 10: Documentation Updates

Files:

- `README.md`
- `.env.example`
- `docs/mcp/*.example`
- `docs/release/*`
- `SECURITY.md`

Tasks:

- Replace stale 1.0.0 limitation text.
- Add exact full-text workflow:
  1. `knowcran discover`
  2. `knowcran download-topic`
  3. `knowcran parse-topic`
  4. `knowcran read-topic --fulltext`
  5. `knowcran review --fulltext`
  6. `knowcran search-fulltext`
- Document `run-topic` as the recommended path once fixed.
- Add examples for `legal_only`, `oa_first`, `fastest`, and `scihub_only`.
- Document output directory structure.
- Document MCP readonly vs curate vs admin profiles.

Acceptance:

- A new user can run the README Quick Start from a fresh checkout.

## Recommended Implementation Order

1. Fix `DownloadResult` payload bug and add downloader tests.
2. Add CLI `--fulltext` flags and tests.
3. Fix FTS rebuild idempotency and tests.
4. Add direct OA URL source.
5. Make `run-topic` call a single shared workflow.
6. Add full-text extraction into workflow.
7. Complete Robin-style output artifacts.
8. Harden MCP readonly/curate/admin profiles.
9. Add migration/versioning safety.
10. Update README, `.env.example`, and release docs.
11. Add CI release gates.
12. Run a fresh end-to-end smoke test.

## Minimum Viable Production Patch

If you want the smallest patch that makes the current release usable, do these first:

- Fix `DownloadResult` bytes storage.
- Add `--fulltext` to CLI read/review commands.
- Fix `sync_chunk_fts()` to be idempotent.
- Make `run-topic` call `read_topic(..., fulltext=True)` before review.
- Add direct `openAccessPdf.url` support.
- Add one integration test that proves download -> parse -> search -> read -> review works with a fixture PDF.

## Validation Commands

Run locally after implementation:

```bash
python -m pip install -e ".[dev]"
pytest -q
knowcran --help
knowcran init --data-dir data --vault-dir vault
knowcran discover "intracerebral hemorrhage" --limit 5
knowcran download-topic "intracerebral hemorrhage" --limit 2 --strategy legal_only
knowcran parse-topic "intracerebral hemorrhage" --limit 2
knowcran read-topic "intracerebral hemorrhage" --limit 2 --fulltext
knowcran search-fulltext "hematoma expansion" --topic "intracerebral hemorrhage"
knowcran review "intracerebral hemorrhage" --max-papers 2 --fulltext
knowcran run-topic "intracerebral hemorrhage" --limit 5 --strategy legal_only
```

Optional live tests:

```bash
MNEMOSYNE_LIVE_TESTS=1 pytest tests/live/ -q
```

## Open Questions

- Should `run-topic` automatically discover when no papers exist, or require `--discover` to avoid accidental network calls?
- Should Sci-Hub/LibGen remain enabled by default in packaged releases, or only in local `.env.example` for your private workflow?
- Should OCR be added in the next release via `ocrmypdf` or kept as a later optional plugin?

## Final Go/No-Go Criteria

Ship only when:

- README commands match CLI behavior.
- A fixture-based end-to-end test passes without network access.
- A legal-only live arXiv smoke test passes when live tests are enabled.
- Re-running parse/index does not duplicate or break FTS search.
- `run-topic` produces complete artifacts and a valid manifest.
- MCP readonly mode cannot mutate local data or perform network calls.
- The project documents grey-source risk clearly.
