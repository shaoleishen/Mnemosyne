# Design Specification: Mnemosyne Production-Grade MCP Refactoring

Design spec for upgrading the Mnemosyne/KnowCran scientific knowledge base MCP server and data pipelines to meet production-readiness standards.

## User Review Required

> [!IMPORTANT]
> - **Security Boundary**: A new file [security.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/security.py) will strictly validate `data_dir` and `vault_dir` path parameters using a strict subdirectory whitelist. Write operations to unauthorized directories will be rejected.
> - **MCP Profile Allowlists**: MCP servers are split into distinct profiles (`readonly`, `curate`, `admin`). By default, client tools are restricted based on the profile.
> - **Dynamic Schema Generation**: Overriding `__signature__` on registered FastMCP tools enables true flat JSON schema parameters to be exposed to clients, preserving description, required fields, and default values.

---

## Proposed Changes

### 1. Security Layer (Phase 1)

#### [NEW] [security.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/security.py)
Implement strict path validation to prevent path traversal attacks (`..` escapes, absolute path overrides, symlink traversal) and enforce a subdirectory whitelist.
- Check environment variables `KNOWCRAN_DATA_DIR` and `KNOWCRAN_VAULT_DIR`. If not set, use default directories `data` and `vault` relative to the current workspace directory.
- Implement validation helper `resolve_allowed_path(requested_path: str | None, default_root: Path, env_var_name: str) -> Path`.
- In read-only mode, ignore or reject any client-supplied `data_dir`.

### 2. MCP Server Schema & Profiles (Phase 1)

#### [MODIFY] [mcp.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/server/mcp.py)
- Replace generic `**kwargs` handlers with dynamic parameter generation using `inspect.Signature` and `inspect.Parameter`.
- Map the JSON schema properties from `tools.py` directly to Python types with `Annotated` and Pydantic `Field` metadata.
- Group tools by profiles:
  - `serve-mcp-readonly`: Only read-only query and audit tools.
  - `serve-mcp-curate`: Curate and read-only tools.
  - `serve-mcp-admin`: Full access to admin-only and curate tools.
- Configure FastMCP server with the allowed tools based on the active profile.

#### [MODIFY] [tools.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/server/tools.py)
- Keep `tools.py` as the single source of truth for tool definitions.
- Expose the profile mappings (`get_read_only_tools`, `get_all_tools`, etc.) clearly.

### 3. Evidence Traceability & Models (Phase 2)

#### [MODIFY] [models.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/models.py)
- Extend `EvidenceMatrixRow` to include traceability fields: `citation_key`, `evidence_status`, and `source_quote`.

#### [MODIFY] [storage.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/storage.py)
- Convergence of claim inserts: Modify `insert_claim` and `insert_claims` to insert all metadata fields (`claim_hash`, `source_text_hash`, `extraction_method`, `citation_key`, `source_span_json`, `is_placeholder`, `evidence_status`, `source_quote`).
- Compute `claim_hash` and `source_text_hash` automatically when inserting claims.

#### [MODIFY] [reading.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/reading.py)
- Ensure all claims generated from deterministic or LLM extraction flows are stored using the updated `storage.insert_claims` or `storage.upsert_claim_idempotent` with fully populated traceability columns.

### 4. Reliability Layer & Semantics (Phase 3)

#### [MODIFY] [storage.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/storage.py) & [reading.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/reading.py)
- Limit 0 semantics: Interpret `limit=0` as retrieving all matching records (omitting `LIMIT` in SQL queries). Hard-cap at 500 in MCP tools.

#### [MODIFY] [discovery.py](file:///wsl.localhost/Ubuntu-22.04/home/bioshen/Code/Mnemosyne/knowcran/discovery.py)
- If repeated discovery queries are run for a completed topic, return metadata of existing topic papers or `skipped=True` status rather than returning an empty array.

---

## Verification Plan

### Automated Tests
- MCP handshake, schema list, and tools invocation validation:
  `pytest tests/test_mcp_server.py`
- Path security validation testing:
  `pytest tests/test_mcp_server.py -k "security"`
- Data storage and claims traceability:
  `pytest tests/test_storage.py`
- Run all test suites:
  `pytest`

### Manual Verification
- Start the MCP server using `knowcran serve-mcp-readonly` and connect using Claude Desktop / Claude Code. Validate exposed tools and schema.
