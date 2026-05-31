# MCP Fulltext Tools

This document describes the MCP tools available for full-text PDF operations.

## Read-Only Tools

These tools are safe for long-running agent connections.

### knowcran_search_fulltext

Search fulltext chunks using SQLite FTS5.

**Parameters:**
- `query` (required): FTS5 search query
- `topic` (optional): Scope to topic
- `paper_id` (optional): Scope to paper
- `limit` (optional): Max results (default 20)

**Returns:** Matching chunks with paper title, year, page range, section, and chunk metadata.

### knowcran_get_pdf_status

Get PDF download status for a topic or specific paper.

**Parameters:**
- `topic` (optional): Topic to check status for
- `paper_id` (optional): Specific paper ID

**Returns:** Download progress, sources, file paths, and status summary.

### knowcran_get_paper_note

Get a structured paper note with sections for metadata, methods, results, limitations, and evidence quotes.

**Parameters:**
- `paper_id` (required): Paper ID

**Returns:** Structured note with linked claims and chunks.

### knowcran_get_evidence_context

Get evidence context for a claim including source quote, page range, and chunk text.

**Parameters:**
- `claim_id` (required): Claim ID to get context for

**Returns:** Claim details, chunk text, source quote, and evidence status.

### knowcran_get_review_artifacts

Get review artifacts (review markdown, evidence matrix CSV, bibliography, open questions) for a topic.

**Parameters:**
- `topic` (required): Topic name

**Returns:** Review artifacts content.

## Curate Tools

These tools require approval and may mutate data.

### knowcran_download_paper_pdf

Download a PDF for a single paper.

**Parameters:**
- `paper_id` (required): Paper ID
- `strategy` (optional): Download strategy (default: `fastest`)
- `force` (optional): Force re-download even if cached

**Returns:** Download result with source and file path.

### knowcran_download_topic_pdfs

Download PDFs for all papers in a topic.

**Parameters:**
- `topic` (required): Topic to download PDFs for
- `limit` (optional): Max papers (default 20)
- `strategy` (optional): Download strategy

**Returns:** Summary of download results.

### knowcran_parse_paper_pdf

Parse a downloaded PDF into page-aware text chunks.

**Parameters:**
- `paper_id` (required): Paper ID

**Returns:** Chunk count and parse status.

### knowcran_parse_topic_pdfs

Parse all downloaded PDFs for a topic.

**Parameters:**
- `topic` (required): Topic to parse PDFs for
- `limit` (optional): Max papers (default 20)

**Returns:** Summary of parse results.

### knowcran_read_fulltext

Extract claims from a paper's full text (PDF chunks).

**Parameters:**
- `paper_id` (required): Paper ID
- `topic` (optional): Topic to tag claims with

**Returns:** Extracted claims with evidence status.

### knowcran_review_fulltext

Generate a literature review prioritizing full-text claims.

**Parameters:**
- `topic` (required): Topic to review
- `max_papers` (optional): Max papers (default 30)

**Returns:** Review with evidence count and open questions.

### knowcran_run_topic

Run the full pipeline: discover -> download -> parse -> extract -> notes -> review.

**Parameters:**
- `topic` (required): Topic for the pipeline run
- `limit` (optional): Max papers (default 50)
- `strategy` (optional): Download strategy

**Returns:** Structured output directory path and run summary.

## Profile Summary

| Profile | Tools |
| --- | --- |
| readonly | read + audit + fulltext read (12 tools) |
| curate | read + write + audit + fulltext read + fulltext write (24 tools) |
| admin | curate + admin tools |
