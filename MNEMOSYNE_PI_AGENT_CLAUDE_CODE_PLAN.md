# Mnemosyne Pi Agent + Claude Code Integration Plan

Date: 2026-05-28

Target repo: `Mnemosyne-main`

Pi definition used in this plan:

> Pi is a minimal terminal coding harness. It supports interactive, print/JSON, RPC, and SDK modes. It is customized through extensions, skills, prompt templates, themes, and shareable Pi packages via npm or git. It intentionally skips built-in sub-agents and plan mode; workflows should be added as packages or extensions. OpenClaw is the reference-style integration to study.

## Executive Direction

Yes, this plan treats Pi as that agent/harness, not as a generic "PI API".

Mnemosyne should integrate Pi through Pi's actual strengths:

1. Pi print/JSON mode for simple structured agent calls.
2. Pi RPC mode for longer-running or tool-style integration.
3. Pi SDK mode later if the SDK is stable and easier to test.
4. Pi packages for Mnemosyne-specific skills, prompt templates, and workflows.

Claude Code should integrate primarily through Mnemosyne's MCP server, not by forcing Claude Code to mimic Pi.

Claw should remain optional compatibility only.

## Target Architecture

```text
Mnemosyne core
  |
  |-- discovery.py
  |-- reading.py / extraction.py
  |-- review.py
  |-- storage.py
  |-- obsidian.py
  |
  |-- agent provider layer
  |     |-- PiPrintJsonProvider
  |     |-- PiRpcProvider
  |     |-- PiSdkProvider later
  |     |-- ClaudeCodeSubprocessProvider optional
  |     |-- ClawProvider optional
  |     |-- DeterministicProvider
  |
  |-- external surfaces
        |-- MCP server for Claude Code, Cursor, other MCP clients
        |-- CLI for humans and shell automation
        |-- optional HTTP API
        |-- Pi package: skills + prompt templates + commands
```

Rule: Mnemosyne owns data. Pi/Claude/Claw return structured results only.

## Why Pi Fits Mnemosyne

Pi's minimalism is a good match if Mnemosyne keeps the research pipeline deterministic and auditable.

Use Pi for:

- relevance reranking
- claim extraction from abstracts/full text
- review synthesis from evidence matrix
- metadata repair suggestions
- workflow automation around Mnemosyne commands

Do not use Pi for:

- direct SQLite writes
- direct vault mutation
- unvalidated claim insertion
- hidden web/network calls inside default tests
- replacing Mnemosyne's storage or traceability logic

## Integration Modes

### Mode 1: Pi print/JSON provider

Use first. It is the simplest and easiest to test.

Expected shape:

```bash
pi --json "<prompt>"
```

or whatever Pi's real print/JSON command is. CC must verify exact CLI flags from local Pi docs/help.

Provider:

```text
knowcran/agents/pi_print_json_provider.py
```

Responsibilities:

- build a Pi prompt from `AgentTask`
- call Pi in print/JSON mode
- parse stdout as JSON
- if Pi returns an envelope, unwrap the assistant/message field
- validate output against Pydantic schema
- return `AgentResult`

### Mode 2: Pi RPC provider

Use second. This is better for stable machine integration and repeated calls.

Provider:

```text
knowcran/agents/pi_rpc_provider.py
```

Responsibilities:

- start or connect to Pi RPC process
- send `AgentTask` as structured RPC payload
- receive structured response
- handle timeout/retry/error
- avoid one process spawn per paper when processing many papers

Use for:

- batch extraction
- review synthesis
- long-running topic workflows

### Mode 3: Pi SDK provider

Use later only if SDK docs and packaging are stable.

Provider:

```text
knowcran/agents/pi_sdk_provider.py
```

Acceptance:

- can be mocked without Pi installed
- no live model calls in default tests
- same `AgentTask` / `AgentResult` contract

### Mode 4: Pi package for Mnemosyne

This is the Pi-native path.

Create a Pi package that includes:

```text
pi-packages/mnemosyne-research/
  package.json
  README.md
  skills/
    mnemosyne-literature-review.md
    mnemosyne-evidence-audit.md
    mnemosyne-metadata-repair.md
  prompts/
    claim-extraction.json
    relevance-rerank.json
    review-synthesis.json
  extensions/
    mnemosyne-cli.md
```

Purpose:

- teach Pi how to call `mnemosyne` commands
- define output JSON rules
- provide reusable prompt templates
- package Mnemosyne workflows through npm or git

## Core Agent Contract

Add:

```text
knowcran/agents/base.py
knowcran/agents/schemas.py
knowcran/agents/registry.py
```

Schema:

```python
class AgentTask(BaseModel):
    task_id: str
    task_type: Literal[
        "relevance_rerank",
        "claim_extraction",
        "review_synthesis",
        "metadata_repair",
    ]
    topic: str | None = None
    paper_id: str | None = None
    input_json: dict[str, Any]
    output_schema_name: str
    timeout_seconds: int = 600
    trace: dict[str, Any] = Field(default_factory=dict)

class AgentResult(BaseModel):
    task_id: str
    provider: str
    provider_mode: Literal["pi_print_json", "pi_rpc", "pi_sdk", "claude_code", "claw", "deterministic"]
    model: str | None = None
    status: Literal["ok", "error", "timeout", "schema_error"]
    output_json: dict[str, Any] | None = None
    raw_output: str | None = None
    error: str | None = None
    usage_json: dict[str, Any] = Field(default_factory=dict)
```

Provider protocol:

```python
class AgentProvider(Protocol):
    name: str

    def run(self, task: AgentTask) -> AgentResult:
        ...

    def capabilities(self) -> set[str]:
        ...
```

Capabilities:

```text
structured_json
json_schema
rpc
sdk
subprocess
batch
long_context
tool_calls
local_harness
```

## Config

Add:

```text
.mnemosyne/agents.toml
```

Example:

```toml
[agents]
default = "pi-json"
fallback = "deterministic"

[agents.providers.pi-json]
type = "pi_print_json"
command = "${PI_BIN}"
model = "${PI_MODEL}"
timeout_seconds = 600
capabilities = ["structured_json", "subprocess", "local_harness"]

[agents.providers.pi-rpc]
type = "pi_rpc"
command = "${PI_BIN}"
rpc_endpoint = "${PI_RPC_ENDPOINT}"
timeout_seconds = 600
capabilities = ["structured_json", "rpc", "batch", "local_harness"]

[agents.providers.claude-code]
type = "claude_code"
command = "${CLAUDE_CODE_BIN}"
timeout_seconds = 600
capabilities = ["structured_json", "subprocess"]

[agents.providers.deterministic]
type = "deterministic"
capabilities = ["structured_json"]
```

Environment:

```text
MNEMOSYNE_AGENT_PROVIDER=pi-json|pi-rpc|claude-code|deterministic
MNEMOSYNE_AGENT_CONFIG=.mnemosyne/agents.toml
PI_BIN=pi
PI_MODEL=
PI_RPC_ENDPOINT=
CLAUDE_CODE_BIN=claude
```

CLI:

```bash
mnemosyne agents list
mnemosyne agents doctor
mnemosyne agents test --provider pi-json
mnemosyne read-topic "intracerebral hemorrhage" --agent-provider pi-json
mnemosyne review "intracerebral hemorrhage" --agent-provider pi-rpc
```

## Mnemosyne MCP Server For Claude Code

Claude Code should mostly use Mnemosyne as an MCP tool server.

Add:

```text
knowcran/server/mcp.py
knowcran/server/tools.py
```

CLI:

```bash
mnemosyne serve-mcp
```

MCP tools:

```text
mnemosyne_discover
mnemosyne_read_topic
mnemosyne_read_paper
mnemosyne_review
mnemosyne_export_obsidian
mnemosyne_search_papers
mnemosyne_search_claims
mnemosyne_get_topic_papers
mnemosyne_get_evidence_matrix
mnemosyne_get_bibliography
mnemosyne_stats
```

Separate read/write tools:

Read-only:

```text
mnemosyne_search_papers
mnemosyne_search_claims
mnemosyne_get_topic_papers
mnemosyne_get_evidence_matrix
mnemosyne_get_bibliography
mnemosyne_stats
```

Write/network:

```text
mnemosyne_discover
mnemosyne_read_topic
mnemosyne_read_paper
mnemosyne_review
mnemosyne_export_obsidian
```

This makes Claude Code useful immediately without needing Claude Code to become a provider.

## Refactor Core Calls

### discovery.py

Replace `_llm_rerank(...)` with:

```python
task = AgentTask(
    task_type="relevance_rerank",
    topic=topic,
    input_json={"topic": topic, "papers": paper_dicts},
    output_schema_name="PaperRerankOutput",
)
result = provider.run(task)
```

Persist:

- deterministic score
- Pi score
- Pi reason
- provider/mode/model
- run ID

### extraction.py

Replace direct LLM provider call with:

```python
task = AgentTask(
    task_type="claim_extraction",
    topic=topic,
    paper_id=paper["paper_id"],
    input_json={"topic": topic, "paper": paper, "source_text": paper.get("abstract")},
    output_schema_name="PaperExtractionOutput",
)
result = provider.run(task)
```

Persist:

- source quote
- source span
- extraction method
- provider
- run ID
- placeholder flag

### review.py

Use:

```python
task = AgentTask(
    task_type="review_synthesis",
    topic=topic,
    input_json={
        "topic": topic,
        "papers": selected_papers,
        "claims": selected_claims,
        "citation_keys": citation_key_map,
    },
    output_schema_name="ReviewSynthesisOutput",
)
```

Hard rules:

- Pi/Claude/Claw may only cite keys in `citation_keys`.
- invalid citation keys invalidate the agent result.
- fallback must be audited.

## Agent Runs Audit

Add:

```sql
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_mode TEXT NOT NULL,
    model TEXT,
    task_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    input_json TEXT,
    output_schema_name TEXT,
    raw_output TEXT,
    parsed_output_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    usage_json TEXT,
    created_at TEXT NOT NULL
);
```

Every provider call must create a row, including:

- Pi success
- Pi timeout
- Pi malformed JSON
- Pi schema error
- Claude Code provider failure
- deterministic fallback

## Tests

No live Pi, Claude Code, Claw, Semantic Scholar, or LLM calls in default tests.

Add:

```text
tests/test_agent_schemas.py
tests/test_agent_registry.py
tests/test_pi_print_json_provider.py
tests/test_pi_rpc_provider.py
tests/test_agent_audit.py
tests/test_mcp_server_tools.py
tests/test_core_agent_refactor.py
```

Pi print/JSON tests:

- direct JSON stdout
- JSON envelope with `message`
- markdown fenced JSON
- malformed JSON
- nonzero exit
- timeout
- schema invalid
- long prompt via stdin/temp file, not argv

Pi RPC tests:

- sends valid `AgentTask`
- receives valid `AgentResult`
- timeout
- connection failure
- batch extraction mock

MCP tests:

- read-only tools do not write
- write tools call correct core function
- tool schemas include `data_dir` and `vault_dir`
- evidence matrix is returned as structured JSON

## PR Order For CC

### PR 1: AgentTask / AgentResult Foundation

- Add `knowcran/agents`.
- Add provider protocol and registry.
- Add config loader for `.mnemosyne/agents.toml`.
- Add deterministic provider.
- Keep old `knowcran/llm` compatibility wrapper.

### PR 2: Pi Print/JSON Provider

- Add `PiPrintJsonProvider`.
- Detect `PI_BIN`.
- Parse direct JSON, envelope JSON, and fenced JSON.
- Use stdin/temp file for large prompts.
- Add fake subprocess tests.

### PR 3: Agent Audit

- Add `agent_runs`.
- Log every provider call.
- Add CLI visibility for last failures.
- Stop hardcoding provider as `claw`.

### PR 4: Refactor Discovery / Extraction / Review

- Replace LLM-specific calls with `AgentTask`.
- Preserve deterministic fallback.
- Store Pi scores/reasons separately.
- Validate citations.

### PR 5: Pi RPC Provider

- Add `PiRpcProvider`.
- Support batch tasks.
- Add fake RPC tests.

### PR 6: Claude Code MCP Server

- Add `mnemosyne serve-mcp`.
- Add MCP tools.
- Document Claude Code setup.

### PR 7: Pi Package

- Add `pi-packages/mnemosyne-research`.
- Include skills and prompt templates.
- Add install docs for npm/git package usage.

### PR 8: Docs And Smoke Tests

- README update.
- `docs/pi-integration.md`
- `docs/claude-code-mcp.md`
- `docs/agent-runs-audit.md`
- offline mocked end-to-end tests.

## Prompt To Give CC

```text
You are working in Mnemosyne-main.

Important correction: PI means Pi, the minimal terminal coding harness with interactive, print/JSON, RPC, and SDK modes. It supports extensions, skills, prompt templates, themes, and shareable Pi packages via npm or git. It is not a generic HTTP provider.

Goal: make Mnemosyne integrate with Pi as the primary agent harness and Claude Code through MCP, while keeping Claw optional only.

Implement:
1. Provider-neutral AgentTask / AgentResult / AgentProvider contracts.
2. PiPrintJsonProvider first.
3. PiRpcProvider second.
4. Optional PiSdkProvider only if SDK is stable and mockable.
5. Mnemosyne MCP server for Claude Code.
6. agent_runs audit table.
7. Refactor discovery, extraction, and review to use AgentTask.
8. Add Pi package with Mnemosyne skills and prompt templates.

Hard constraints:
- Mnemosyne owns SQLite, vault export, evidence traceability, citation validation, and persistence.
- Pi/Claude/Claw return structured JSON only.
- No live Pi, Claude Code, Claw, Semantic Scholar, or LLM calls in default tests.
- Long prompts must not be passed as one giant argv string.
- Every agent success/failure/fallback must be audited.
- Claude Code should primarily consume Mnemosyne via MCP.
- Claw remains optional compatibility, not the main path.

Definition of done:
- pytest passes offline.
- fake Pi print/JSON provider tests pass.
- fake Pi RPC provider tests pass.
- Mnemosyne MCP server exposes read-only and write tools separately.
- Claude Code can connect through MCP and query papers/claims.
- Pi package exists with skills and prompt templates.
- README explains Pi, Claude Code MCP, deterministic fallback, and optional Claw.
```

## Final Recommendation

Use Pi as the main local agent harness:

- print/JSON for quick structured calls
- RPC for repeated/batch workflows
- SDK later if it becomes the cleanest stable path
- Pi package for Mnemosyne-specific workflows

Use Claude Code as the main operator through MCP.

Keep Claw as optional compatibility only.

