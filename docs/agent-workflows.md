# Agent Workflows

This document describes how to use Mnemosyne with agent clients like Codex, Claude Code, and Claude Desktop.

## MCP Server Setup

### Claude Code

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "knowcran": {
      "command": "knowcran",
      "args": ["serve-mcp-readonly"],
      "type": "stdio"
    }
  }
}
```

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "knowcran": {
      "command": "knowcran",
      "args": ["serve-mcp-readonly"],
      "transport": "stdio"
    }
  }
}
```

### Codex

Add to your `codex.toml`:

```toml
[mcp_servers.knowcran]
command = "knowcran"
args = ["serve-mcp-readonly"]
```

## Workflow Examples

### Research Assistant

A typical research workflow using Mnemosyne MCP tools:

1. **Discover papers**: `knowcran_discover` to search for papers on a topic
2. **Download PDFs**: `knowcran_download_topic_pdfs` to get full text
3. **Parse PDFs**: `knowcran_parse_topic_pdfs` to extract text chunks
4. **Extract claims**: `knowcran_read_fulltext` to get structured claims
5. **Search evidence**: `knowcran_search_fulltext` to find specific information
6. **Generate review**: `knowcran_review_fulltext` to create a literature review

### Evidence-Based Answer Generation

When answering questions about a topic:

1. Search for relevant chunks: `knowcran_search_fulltext`
2. Get evidence context: `knowcran_get_evidence_context` for each claim
3. Check evidence status: Ensure claims are from full text, not just abstracts
4. Cite sources: Use citation keys and page numbers from the evidence
5. Audit answer: `knowcran_audit_answer` to check for overclaims

### Topic Exploration

For exploring a new research area:

1. Run the full pipeline: `knowcran_run_topic`
2. Review the output directory structure
3. Examine the evidence matrix for coverage gaps
4. Use `knowcran_search_fulltext` to drill into specific findings
5. Generate notes: `knowcran_get_paper_note` for key papers

## Best Practices

### For Agents

- Always check `evidence_status` before making strong claims
- Prefer `full_text_reviewed` claims over `abstract_only`
- Use `source_quote` for direct citations
- Include page numbers when referencing specific findings
- Run `knowcran_audit_answer` before presenting conclusions

### For Users

- Start with `knowcran serve-mcp-readonly` for safety
- Use `--limit` to control how many papers are processed
- Check `knowcran pdf-status` before running full-text operations
- Use `knowcran search-fulltext` to verify findings
- Review the evidence matrix in the output directory

## Error Handling

Common errors and solutions:

| Error | Solution |
| --- | --- |
| "Paper not found" | Run `knowcran discover` first |
| "No downloaded PDF" | Run `knowcran download-topic` first |
| "No chunks available" | Run `knowcran parse-topic` first |
| "FTS search failed" | Ensure chunks are parsed and FTS is synced |
| "All sources failed" | Check network connectivity and source availability |
