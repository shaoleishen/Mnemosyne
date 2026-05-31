# KnowCran / Mnemosyne MCP Integration Refactor Plan

## 1. Goal

把 KnowCran / Mnemosyne 改造成一个可被 Claude Code、Codex、Claude Desktop 等 MCP 客户端稳定调用的本地科研知识库工具服务器。

核心定位不是“让 agent 自动写知识”，而是让 agent 通过 MCP 访问一个可追溯的证据库：论文、claims、evidence matrix、bibliography、review draft、open questions 都必须来自本地数据库或明确的外部检索结果。

## 2. Current State

当前项目已经具备 MCP 雏形：

- CLI 入口：`knowcran serve-mcp`
- MCP 实现：`knowcran/server/mcp.py`
- MCP 工具定义：`knowcran/server/tools.py`
- 数据来源：SQLite `knowcran.sqlite`
- 输出目标：Obsidian vault
- 现有工具：
  - `mnemosyne_search_papers`
  - `mnemosyne_search_claims`
  - `mnemosyne_get_topic_papers`
  - `mnemosyne_get_evidence_matrix`
  - `mnemosyne_get_bibliography`
  - `mnemosyne_stats`
  - `mnemosyne_discover`
  - `mnemosyne_read_topic`
  - `mnemosyne_read_paper`
  - `mnemosyne_review`
  - `mnemosyne_export_obsidian`

主要问题：

- MCP server 是手写 JSON-RPC 循环，长期兼容性弱。
- 只读工具和联网/写入工具混在同一个 server 中。
- 工具返回结果缺少分页、截断、`response_format`、证据等级等字段。
- citation / claim traceability 还可以更严格。
- 缺少 Claude Code / Codex 的即用配置样例。
- 缺少 MCP 级别的测试和 agent 使用评测。

## 3. Scope

### In Scope

- 用官方 Python MCP SDK 或 FastMCP 重写 MCP server。
- 将 MCP 工具分成只读 server 和 curate/write server。
- 强化 evidence matrix、citation key、claim id、source quote 的返回结构。
- 增加防幻觉审计工具。
- 提供 Claude Code、Codex、Claude Desktop 的配置模板。
- 增加 MCP 协议测试、工具单测、端到端 smoke test。

### Out of Scope

- 不在第一阶段实现完整 PDF full-text ingestion。
- 不在第一阶段实现复杂 multi-agent 编排。
- 不把 LLM 输出直接写入最终知识库，除非通过 schema 和 evidence audit。
- 不做远程 HTTP MCP 部署，先以本地 stdio MCP 为主。

## 4. Target Architecture

```text
Claude Code / Codex / Claude Desktop
        |
        | MCP stdio
        v
knowcran-readonly MCP server
        |
        | read-only queries
        v
SQLite + Obsidian vault

Claude Code / Codex
        |
        | MCP stdio, explicit approval
        v
knowcran-curate MCP server
        |
        | discover / extract / export / review
        v
Semantic Scholar + SQLite + vault
```

建议拆成两个 MCP server：

1. `knowcran-readonly`
   - 默认给 Claude Code / Codex 长期开启。
   - 只允许查询数据库和证据矩阵。
   - 不联网、不写文件、不改数据库。

2. `knowcran-curate`
   - 需要人工审批或按需开启。
   - 允许 discover、read-topic、review、export-obsidian。
   - 会联网、写 SQLite、写 vault，因此必须更谨慎。

## 5. Tool Design

### 5.1 Readonly Tools

#### `knowcran_search_papers`

用途：按 topic 或关键词查论文。

关键参数：

- `query`
- `topic`
- `limit`
- `offset`
- `response_format`: `json | markdown`

返回字段：

- `paper_id`
- `title`
- `year`
- `venue`
- `doi`
- `pmid`
- `citation_key`
- `relevance_score`
- `evidence_status`
- `has_more`
- `next_offset`

#### `knowcran_search_claims`

用途：按 topic、paper、evidence_type 查 claim。

关键参数：

- `topic`
- `paper_id`
- `evidence_type`
- `limit`
- `offset`
- `min_confidence`
- `response_format`

返回字段：

- `claim_id`
- `paper_id`
- `citation_key`
- `claim_text`
- `evidence_type`
- `confidence`
- `source_location`
- `source_quote`
- `source_span`
- `evidence_status`

#### `knowcran_get_evidence_matrix`

用途：返回一个 topic 的证据矩阵，供 agent 写综述、回答问题、生成 gap map。

关键参数：

- `topic`
- `max_papers`
- `evidence_types`
- `response_format`
- `include_quotes`
- `include_open_questions`

返回字段：

- `topic`
- `paper_count`
- `claim_count`
- `evidence_matrix`
- `coverage_summary`
- `limitations`
- `has_abstract_only_evidence`

#### `knowcran_get_bibliography`

用途：返回某 topic 的 BibTeX 或 citation key map。

关键参数：

- `topic`
- `format`: `bibtex | json`

返回字段：

- `citation_key`
- `title`
- `year`
- `doi`
- `pmid`
- `bibtex`

#### `knowcran_stats`

用途：检查知识库健康状况。

返回字段：

- `papers`
- `claims`
- `topics`
- `links`
- `agent_runs`
- `last_updated`

### 5.2 Curate / Write Tools

#### `knowcran_discover`

用途：从 Semantic Scholar 检索并入库。

保护措施：

- 默认 `limit <= 50`
- `expand=false` 默认关闭
- 返回检索摘要，不直接生成结论
- 记录 raw API cache 和 search query

#### `knowcran_read_topic`

用途：从已入库论文抽取 claims。

保护措施：

- 默认 deterministic extraction。
- LLM extraction 需要显式参数启用。
- 每条 claim 必须有 `source_quote` 或 `full_text_needed` 标记。

#### `knowcran_review`

用途：从 stored claims 生成 review draft。

保护措施：

- LLM 只能使用 selected claims。
- citation key 必须在白名单内。
- 输出必须经过 citation validation。
- 若校验失败，回退 deterministic review。

#### `knowcran_export_obsidian`

用途：导出 vault notes。

保护措施：

- 只写入配置的 vault directory。
- 输出写入计数和文件列表。
- 不覆盖用户手写内容，除非使用明确的 generated block 或 generated files。

## 6. Anti-Hallucination Design

### 6.1 Evidence Contract

所有 agent 可用事实必须来自以下结构之一：

- `paper_id`
- `claim_id`
- `citation_key`
- `source_quote`
- `source_span`
- `evidence_type`
- `evidence_status`

禁止 agent 输出：

- 数据库中不存在的 DOI、PMID、样本量、年份、作者、结果。
- 没有 claim 支撑的因果结论。
- 把 abstract-only claim 写成 full-text verified conclusion。
- 把 animal model / in vitro evidence 直接外推成人类临床结论。

### 6.2 Evidence Status

建议给每条 claim 增加 `evidence_status`：

- `metadata_only`
- `abstract_only`
- `full_text_reviewed`
- `direct_evidence`
- `adjacent_background`
- `candidate_only`
- `needs_manual_review`

### 6.3 Add Audit Tool

新增工具：`knowcran_audit_answer`

用途：检查 agent 已生成回答是否被 evidence matrix 支撑。

输入：

- `topic`
- `answer_text`
- `strict`: boolean

输出：

- `supported_claims`
- `unsupported_claims`
- `missing_citations`
- `invalid_citations`
- `overclaim_risks`
- `recommended_revision`

审计规则：

- 每个事实句至少对应一个 claim。
- 每个 citation key 必须存在。
- 临床、因果、机制、疗效类表达必须有对应证据等级。
- 不足证据时建议改写为不确定表达。

## 7. Implementation Phases

### Phase 1: Stabilize MCP Server

- Add official MCP Python SDK dependency.
- Replace hand-written JSON-RPC loop in `knowcran/server/mcp.py`.
- Keep `knowcran serve-mcp` as CLI entrypoint.
- Move shared handlers into reusable service functions.
- Ensure all logs go to stderr, never stdout.
- Add smoke test for `initialize`, `tools/list`, and one `tools/call`.

### Phase 2: Split Readonly and Curate Servers

- Add `knowcran serve-mcp-readonly`.
- Add `knowcran serve-mcp-curate`.
- Keep `serve-mcp` as compatibility alias, but document it as all-tools mode.
- Mark tools with annotations:
  - read-only tools: `readOnlyHint=true`
  - network tools: `openWorldHint=true`
  - write tools: `readOnlyHint=false`
  - export tools: `destructiveHint=false`, `idempotentHint=true` when safe

### Phase 3: Improve Tool Schemas and Responses

- Add `limit`, `offset`, `has_more`, `next_offset`.
- Add `response_format=json|markdown`.
- Add character limit and truncation metadata.
- Add `citation_key`, `claim_id`, `source_quote`, `source_span`.
- Add actionable error messages.
- Validate `data_dir` and `vault_dir` path scope.

### Phase 4: Strengthen Evidence Traceability

- Add or backfill `citation_key` on claims.
- Add `evidence_status`.
- Add `source_quote` and `source_span_json` wherever possible.
- Update review synthesis to require citation key whitelist validation.
- Reject outputs with invalid citation keys.
- Add deterministic fallback for failed LLM synthesis.

### Phase 5: Add Audit Workflow

- Implement `knowcran_audit_answer`.
- Add paragraph-level claim traceability output.
- Add overclaim risk labels:
  - `unsupported_fact`
  - `invalid_citation`
  - `abstract_only_overclaim`
  - `animal_to_human_overclaim`
  - `correlation_to_causation`
  - `missing_uncertainty`
- Add tests with deliberately hallucinated answers.

### Phase 6: Client Config Templates

- Add `docs/mcp/codex.config.toml.example`.
- Add `docs/mcp/claude-code.mcp.json.example`.
- Add `docs/mcp/claude-desktop.config.json.example`.
- Document Windows PowerShell paths and `uv` usage.
- Document recommended readonly-first setup.

### Phase 7: Evaluation and QA

- Add MCP integration tests.
- Add CLI smoke tests.
- Add 10 evaluation questions that require multiple MCP calls.
- Add tests for:
  - pagination
  - response truncation
  - citation validation
  - invalid path rejection
  - readonly server excluding write tools
  - curate server exposing write tools

## 8. Recommended Client Configs

### 8.1 Codex Config Example

```toml
[mcp_servers.knowcran]
command = "uv"
args = [
  "--directory",
  "E:\\KNOWCRAN\\Mnemosyne-feat-agent-llm-integration",
  "run",
  "knowcran",
  "serve-mcp-readonly"
]
startup_timeout_sec = 20
tool_timeout_sec = 120
enabled = true

[mcp_servers.knowcran.env]
KNOWCRAN_DATA_DIR = "E:\\KNOWCRAN\\knowtest\\data"
KNOWCRAN_VAULT_DIR = "E:\\KNOWCRAN\\knowtest\\vault"
```

### 8.2 Claude Code Project Config Example

```json
{
  "mcpServers": {
    "knowcran": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "E:\\KNOWCRAN\\Mnemosyne-feat-agent-llm-integration",
        "run",
        "knowcran",
        "serve-mcp-readonly"
      ],
      "env": {
        "KNOWCRAN_DATA_DIR": "E:\\KNOWCRAN\\knowtest\\data",
        "KNOWCRAN_VAULT_DIR": "E:\\KNOWCRAN\\knowtest\\vault"
      }
    }
  }
}
```

### 8.3 Optional Curate Server

```json
{
  "mcpServers": {
    "knowcran-curate": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "E:\\KNOWCRAN\\Mnemosyne-feat-agent-llm-integration",
        "run",
        "knowcran",
        "serve-mcp-curate"
      ],
      "env": {
        "KNOWCRAN_DATA_DIR": "E:\\KNOWCRAN\\knowtest\\data",
        "KNOWCRAN_VAULT_DIR": "E:\\KNOWCRAN\\knowtest\\vault"
      }
    }
  }
}
```

## 9. Testing Plan

### Unit Tests

- Tool schema generation.
- Tool handler parameter validation.
- Evidence matrix formatting.
- Citation key validation.
- Audit answer logic.

### Integration Tests

- Start MCP server through stdio.
- Call `initialize`.
- Call `tools/list`.
- Call `knowcran_stats`.
- Call `knowcran_get_evidence_matrix`.
- Assert readonly server does not list curate tools.

### Manual Smoke Tests

```powershell
uv --directory E:\KNOWCRAN\Mnemosyne-feat-agent-llm-integration run knowcran stats --data-dir E:\KNOWCRAN\knowtest\data
uv --directory E:\KNOWCRAN\Mnemosyne-feat-agent-llm-integration run knowcran serve-mcp-readonly
```

### Agent Evaluation Questions

Create evaluations such as:

1. Which claims about intracerebral hemorrhage are based only on abstracts?
2. Which papers support NLRP3 inflammasome involvement, and what evidence type are they?
3. What open questions remain for animal model translation?
4. Which claims mention hematoma expansion?
5. Which conclusions would be overclaims if written as clinical recommendations?

## 10. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Agent treats abstract-only evidence as full evidence | High | Add `evidence_status` and audit tool |
| MCP response too large | Medium | Pagination and truncation |
| Client rejects hand-written MCP protocol | High | Use official MCP SDK |
| Write tools accidentally mutate vault | Medium | Split readonly / curate servers |
| Invalid citation keys in review | High | Whitelist citation validation |
| Windows path issues | Medium | Add explicit config examples |
| Network rate limits | Medium | Cache Semantic Scholar responses and default low limits |

## 11. Acceptance Criteria

The refactor is complete when:

- Claude Code and Codex can both list KnowCran MCP tools.
- Readonly server exposes only read-only tools.
- Curate server exposes discover/read/review/export tools separately.
- `knowcran_get_evidence_matrix` returns claim-level traceability.
- `knowcran_audit_answer` can flag unsupported or overclaimed statements.
- LLM review synthesis cannot use invalid citation keys.
- Smoke tests pass on Windows.
- Documentation includes ready-to-copy Codex and Claude Code config examples.

## 12. Suggested Implementation Order

1. Add official MCP SDK dependency.
2. Rebuild `knowcran/server/mcp.py` around SDK primitives.
3. Add `serve-mcp-readonly` and `serve-mcp-curate`.
4. Improve read tool schemas and pagination.
5. Add traceability fields to evidence matrix output.
6. Add `knowcran_audit_answer`.
7. Add client config examples under `docs/mcp/`.
8. Add MCP integration tests.
9. Run local client smoke tests in Codex and Claude Code.
10. Only then enable curate/write tools by default in trusted projects.
