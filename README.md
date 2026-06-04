# Mnemosyne / KnowCran

**Status: 1.0.0 production release candidate**

Mnemosyne, packaged as `knowcran`, is a local scientific evidence knowledge base for literature discovery, traceable claim extraction, evidence matrices, review drafting, Obsidian export, and MCP access from agent clients such as Codex, Claude Code, and Claude Desktop.

The project is designed for local-first research workflows. It stores paper metadata, claims, citations, runs, and generated artifacts in SQLite and plain files. Semantic Scholar is the primary discovery source. LLM/agent extraction is optional; deterministic extraction remains the default fallback.

## What 1.0.0 Means

Version 1.0.0 is the first production-baseline release. It does not mean cloud multi-tenancy or polished academic prose generation. It does mean:

- repeatable local install and test workflow
- explicit Apache-2.0 license
- stable CLI entry points: `knowcran` and `mnemosyne`
- readonly, curate, and admin MCP profiles
- optional full-text PDF ingestion with local parsing, chunking, FTS5 indexing, and hybrid search
- managed local service startup for MinerU and OpenAI-compatible local embeddings when configured
- evidence traceability through `paper_id`, `claim_id`, `citation_key`, `source_quote`, and `evidence_status`
- SQLite migrations for existing local databases
- cached, rate-limited Semantic Scholar access with retry behavior
- CI-ready unit, integration, MCP, and packaging checks

## Features

| Area | Capability |
| --- | --- |
| Discovery | Search Semantic Scholar, cache raw responses, deduplicate papers, and store topic membership. |
| Reading | Extract claims from abstracts with deterministic fallback and optional agent/LLM providers. |
| Evidence | Build evidence matrices with citation keys, source quotes, evidence status, and coverage summaries. |
| Full Text | Download PDFs, parse pages with MinerU or PyMuPDF, slice chunks, index FTS5, and optionally embed locally. |
| Search | Run keyword full-text search or hybrid RRF search over FTS5 and dense embeddings. |
| Review | Generate evidence digests and review drafts from stored claims. |
| Obsidian | Export papers, claims, topics, reviews, CSV evidence matrices, and BibTeX. |
| MCP | Serve readonly, curate, and admin MCP profiles for agent clients. |
| Audit | Validate citations and detect common overclaim risks in generated answers. |

## Installation

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
knowcran init
```

Python 3.12 or newer is required.

For published packages, use `pip install knowcran` for the core CLI and MCP server, or `pip install "knowcran[local,rag]"` for managed local embeddings and RAG features.

## Quick Start

```bash
# Discover literature.
knowcran discover "intracerebral hemorrhage" --limit 100

# Extract claims. Use --limit 0 to process all available topic papers.
knowcran read-topic "intracerebral hemorrhage" --limit 50

# Generate a traceable review draft.
knowcran review "intracerebral hemorrhage" --max-papers 50

# Run the local PDF/RAG pipeline when MinerU/embedding services are configured.
knowcran run-topic "intracerebral hemorrhage" --limit 50 --gpu

# Export Obsidian notes and review artifacts.
knowcran export-obsidian "intracerebral hemorrhage"

# Inspect local database health.
knowcran stats
```

## Configuration

Environment variables are read from `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `SEMANTIC_SCHOLAR_API_KEY` | empty | Optional Semantic Scholar API key. |
| `KNOWCRAN_DATA_DIR` | `data` | Directory for SQLite database and raw API cache. |
| `KNOWCRAN_VAULT_DIR` | `vault` | Directory for Obsidian export. |
| `KNOWCRAN_RATE_LIMIT_SECONDS` | `1.1` | Minimum delay between Semantic Scholar requests. |
| `MNEMOSYNE_LLM_PROVIDER` | `none` | LLM provider: `none` or `claw`. |
| `MNEMOSYNE_CLAW_BIN` | auto-detect | Optional path to the Claw binary. |
| `MNEMOSYNE_CLAW_MODEL` | `sonnet` | Model label passed to Claw. |
| `MNEMOSYNE_CLAW_PERMISSION_MODE` | `read-only` | Permission mode for Claw subprocess calls. |
| `MNEMOSYNE_CLAW_TIMEOUT_SECONDS` | `600` | Timeout for LLM subprocess calls. |
| `MNEMOSYNE_CLAW_MAX_RETRIES` | `2` | Max retries for LLM subprocess calls. |
| `MNEMOSYNE_LLM_CACHE_DIR` | `data/raw/llm` | Directory for LLM run artifacts. |
| `MNEMOSYNE_PDF_DOWNLOAD_ENABLED` | `true` | Enable or disable full-text PDF download workflow. |
| `MNEMOSYNE_PDF_DIR` | `data/pdfs` | Directory for caching downloaded PDF files. |
| `MNEMOSYNE_PDF_STRATEGY` | `fastest` | Download precedence (e.g., direct OA url first, then index sources). |
| `MNEMOSYNE_SCIHUB_ENABLED` | `true` | Enable Sci-Hub fallback search for downloaded papers. |
| `MNEMOSYNE_LIBGEN_ENABLED` | `true` | Enable LibGen fallback search for downloaded papers. |
| `MNEMOSYNE_PDF_BATCH_WORKERS` | `5` | Concurrent PDF download worker count. |
| `MNEMOSYNE_PDF_PARSER` | `auto` | PDF parser: `auto` (probes MinerU health, falls back to PyMuPDF), `mineru`, or `pymupdf`. |
| `MINERU_API_URL` / `MNEMOSYNE_MINERU_URL` | `http://127.0.0.1:8000` | Local or remote MinerU API endpoint url. |
| `MNEMOSYNE_MINERU_MODE` | `managed` | MinerU running mode: `managed`, `external`, or `off`. |
| `MNEMOSYNE_MINERU_BACKEND` | `docker` | Managed MinerU backend: `docker` (WSL2/Linux) or `subprocess`. |
| `MNEMOSYNE_MINERU_GPU` | `false` | Enable GPU acceleration reservations inside MinerU container. |
| `MNEMOSYNE_MINERU_WORKERS` | `1` | Max parsing concurrency worker count (prevents VRAM OOM). |
| `MNEMOSYNE_EMBEDDING_PROVIDER` | `openai` | Embedding provider: `openai`, `local`, or `none` (degraded/FTS5-only mode). |
| `MNEMOSYNE_EMBEDDING_MODEL` | `text-embedding-3-large` | Model label used for generating semantic chunk vectors. |
| `MNEMOSYNE_EMBEDDING_API_BASE` | `https://api.openai.com/v1` | Custom API base url for OpenAI-compatible embeddings. |
| `MNEMOSYNE_LOCAL_EMBEDDING_MODE` | `managed` | Local embeddings mode: `managed` (starts server automatically) or `external`. |
| `MNEMOSYNE_LOCAL_EMBEDDING_URL` | `http://127.0.0.1:8010/v1` | Endpoint URL for the local embedding server. |
| `MNEMOSYNE_LOCAL_EMBEDDING_MODEL`| `BAAI/bge-m3` | Model name for local embeddings (e.g. `BAAI/bge-m3`). |
| `MNEMOSYNE_LOCAL_EMBEDDING_DEVICE`| `cpu` | Device backend for local embeddings: `cpu` or `cuda`. |
| `MNEMOSYNE_LOCAL_EMBEDDING_BATCH_SIZE`| `16` | Batch size constraint for local vector generation. |
| `MNEMOSYNE_LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS` | `180` | Managed local embedding startup wait time. |
| `MNEMOSYNE_MINERU_STARTUP_TIMEOUT_SECONDS` | `180` | Managed MinerU startup wait time. |

## Local Managed Services (Local Production Mode)

Mnemosyne can automatically manage background dependencies (MinerU and a local OpenAI-compatible embedding server) once the local prerequisites are installed and configured.

### Prerequisites

To use local CPU or GPU acceleration, install the `local` packages extra:
```bash
pip install -e ".[local]"
```

If you plan to utilize CUDA GPU acceleration, ensure `torch` with CUDA is installed (e.g., via `pip install torch --index-url https://download.pytorch.org/whl/cu124` for CUDA 12.4).

### Docker Image for MinerU

Because MinerU does not publish a pre-built image to Docker Hub, you must build the `mineru:latest` image locally before using the managed Docker backend:
```bash
# Download the global Dockerfile from the official repository
wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile

# Build the local Docker image
docker build -t mineru:latest -f Dockerfile .
```

### Local Embedding Model Cache

When using `MNEMOSYNE_EMBEDDING_PROVIDER=local`, the server will dynamically download `BAAI/bge-m3` on its first run and cache it. To download it ahead of time for offline execution, run:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

### Managing Services

Background services are automatically started on pipeline runs (e.g., `knowcran run-topic`), but they can also be controlled manually via the CLI:

```bash
# Check environment diagnostics and service health
knowcran doctor
knowcran doctor --gpu

# Start services (managed Docker compose / Python embedding subprocesses)
knowcran services start
knowcran services start --gpu

# Check running processes and container details
knowcran services status

# Stop all background managed processes
knowcran services stop

# Tail service execution logs
knowcran services logs mineru
knowcran services logs embedding
```

The local embedding API base may end in `/v1` for OpenAI compatibility; service health checks still probe the service root `/health`.

### Running the Topic Pipeline with GPU

```bash
knowcran run-topic "intracerebral hemorrhage" --limit 50 --gpu
```
The `--gpu` option automatically overrides service devices to CUDA/GPU modes.

For WSL2 + Conda + NVIDIA workstation setup, see `docs/local-wsl-gpu-setup.md`.

## Sci-Hub & LibGen Compliance Disclaimer

> [!WARNING]
> **Copyright and Legal Warning**:
> - Mnemosyne defaults to enabling Sci-Hub and LibGen integrations (`MNEMOSYNE_SCIHUB_ENABLED=true` and `MNEMOSYNE_LIBGEN_ENABLED=true`) to assist researchers in retrieving academic materials.
> - Downloading copyrighted scientific papers through these unauthorized index sources may violate intellectual property or copyright laws depending on your jurisdiction.
> - **The authors and contributors of Mnemosyne assume no liability for user activities.**
> - Direct open-access PDF URLs from paper metadata are tried before the multi-source downloader. After that, source order depends on the selected strategy; use `--strategy legal_only` to avoid unauthorized sources.
> - To completely turn off unauthorized sources, modify your `.env` file to set:
>   ```env
>   MNEMOSYNE_SCIHUB_ENABLED=false
>   MNEMOSYNE_LIBGEN_ENABLED=false
>   ```


## MCP Server Profiles

Use readonly by default for long-running agent sessions.

```bash
# Safe default: read-only queries, evidence matrices, bibliography, and audit tools.
knowcran serve-mcp-readonly

# Curate mode: discovery, reading, review, and export.
knowcran serve-mcp-curate

# Admin mode: local repair and dedupe workflows.
knowcran serve-mcp-admin
```

Client templates are available under `docs/mcp/`:

- `docs/mcp/codex.config.toml.example`
- `docs/mcp/claude-code.mcp.json.example`
- `docs/mcp/claude-desktop.config.json.example`

## Evidence Contract

Mnemosyne treats every generated claim as provisional unless it can be traced to stored evidence. Agent-facing outputs should preserve:

- `paper_id`
- `claim_id`
- `citation_key`
- `claim_text`
- `evidence_type`
- `confidence`
- `source_quote` or `evidence_status`

Abstract-only evidence is explicitly marked. Review and answer generation should not present abstract-only or animal-model evidence as full clinical proof.

## Testing

```bash
pytest -v
pytest --cov=knowcran --cov-report=term-missing
```

The CI workflow runs tests on Linux, macOS, and Windows for Python 3.12 and 3.13, then builds a source distribution and wheel.

## Limitations

- Full-text PDF ingestion is optional and locally managed, requiring external or managed background services (such as MinerU and local embedding server) to be configured.
- Semantic Scholar metadata can be incomplete or rate-limited.
- Deterministic extraction is conservative and may miss nuanced claims.
- Optional LLM/agent providers must return schema-valid JSON before their output is stored.
- Review output is evidence-controlled drafting support, not a substitute for expert literature review.

## Release Documents

- `CHANGELOG.md`
- `ROADMAP.md`
- `CONTRIBUTING.md`
- `docs/local-wsl-gpu-setup.md`
- `docs/fulltext-migration-notes.md`
- `docs/release/1.0.0-checklist.md`
- `.github/workflows/release.yml` publishes tagged releases to GitHub Releases and PyPI.

## License

Apache-2.0. See `LICENSE`.
