# Security Policy

Mnemosyne / KnowCran is a local-first research tool. Most risks come from path handling, local secrets, external API calls, and agent-facing write operations.

## Supported Versions

| Version | Supported |
| --- | --- |
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

## Non-Goals

This project is not a hosted multi-tenant service and does not provide clinical decision support.
