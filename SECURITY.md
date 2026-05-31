# Security Policy

Mnemosyne / KnowCran is a local-first research tool. Most risks come from path handling, local secrets, external API calls, PDF downloads, and agent-facing write operations.

## Supported Versions

| Version | Supported |
| --- | --- |
| 1.1.x | Yes |
| 1.0.x | Yes |
| < 1.0.0 | No security support commitment |

## Reporting A Vulnerability

Open a private security advisory on GitHub when available, or contact the maintainer privately before publishing exploit details.

Please include:

- affected version or commit
- operating system
- command or MCP tool involved
- reproduction steps
- expected and actual impact
- whether secrets, local files, SQLite data, or generated vault output were exposed or modified

## Security Boundaries

- `.env` files must never be committed.
- MCP readonly mode must not mutate SQLite data, write files, or perform network discovery.
- Curate and admin MCP modes are local trusted workflows and should be enabled deliberately.
- `data_dir` and `vault_dir` supplied through MCP are validated against configured roots.
- Optional LLM/agent providers should run in read-only permission mode unless the user explicitly chooses otherwise.
- Downloaded PDFs are stored in `data/pdfs/` which is gitignored and never committed.
- PDF files are validated before storage (magic bytes, size limits, EOF marker).

## PDF Download Risks

### Compliance Risk

Default mode enables Sci-Hub and LibGen as PDF sources. These sources may not comply with publisher terms of service.

**Mitigations:**
- Set `MNEMOSYNE_PDF_STRATEGY=legal_only` for institutional use
- Documentation clearly describes compliance risk at every entry point
- Users can disable grey sources via environment variables

### Malicious PDF Risk

Downloaded PDFs could contain malicious content.

**Mitigations:**
- PDFs are validated by magic bytes and EOF marker before storage
- PDFs are never executed or opened in a browser
- PDFs are only parsed with PyMuPDF for text extraction
- No JavaScript or form processing is performed
- PDFs are stored in a separate directory from the codebase

### Path Traversal Risk

PDF filenames could contain path traversal sequences.

**Mitigations:**
- Filenames are sanitized to remove illegal characters
- PDFs are stored only in the configured `data/pdfs/` directory
- Path boundary validation rejects files outside configured roots

### Network Risk

PDF download sources require network access.

**Mitigations:**
- Each source has a 30-second timeout
- Failed sources are logged but don't block other sources
- Users can disable specific sources via configuration
- No cookies or API keys are required for basic operation

## Non-Goals

This project is not a hosted multi-tenant service and does not provide clinical decision support.
