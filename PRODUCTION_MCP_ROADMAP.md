# Mnemosyne Production MCP Roadmap

本计划目标是把 Mnemosyne/KnowCran 从“可本地试用的科研知识库 MCP”升级为“可长期接入 Claude Code、Codex 等 agent 工具的生产级 MCP 证据底座”。核心原则是：工具 schema 必须真实暴露，写操作必须有安全边界，所有知识输出必须能回溯到 claim、paper、quote 和 citation key。

## Scope

- In: MCP 协议兼容性、安全边界、证据溯源、防幻觉审计、网络可靠性、综述质量、测试与发布验收。
- Out: 大规模云多租户、完整 PDF 全文解析平台、Web UI、商业权限系统。

## Production Readiness Definition

达到生产级 MCP 前，需要满足以下验收条件：

- Claude Code、Codex、Claude Desktop 通过真实 MCP stdio 连接后，可以正确看到所有工具名称、描述、输入 schema、required fields 和 annotations。
- 默认只读模式不允许联网、不允许写库、不允许写出任意路径。
- curate 模式中的 discover/read/review/export 明确分层，并且有路径白名单、超时、限流、重试和可审计 run log。
- 每条 claim 至少包含 `claim_id`、`paper_id`、`topic`、`claim_text`、`evidence_type`、`confidence`、`citation_key`、`source_quote` 或 `evidence_status`。
- 任何由 MCP 返回的综述、回答、evidence matrix 都能追踪到来源论文和来源片段。
- `knowcran_audit_answer` 能识别无引用、无效引用、弱证据强结论、abstract-only 过度表述和 claim 不匹配。
- 测试覆盖真实 MCP handshake、tools/list、tools/call、SQLite migration、路径安全、超时重试和端到端 agent 使用场景。

## Current Blocking Issues

### P0: MCP Schema 可能没有真实暴露

当前 `knowcran/server/tools.py` 定义了 `inputSchema`，但 `knowcran/server/mcp.py` 用动态 `handler(**kwargs)` 注册工具。FastMCP 可能从函数签名推断出宽泛 schema，导致 Claude/Codex 看不到 `required`、enum、默认值和参数说明。

计划：

- 将 MCP 工具注册改为显式 Pydantic input models 或显式 schema registration。
- 保留 `tools.py` 作为单一工具定义源，避免 schema、handler、README 三处漂移。
- 增加真实 MCP stdio 测试，验证 `initialize -> tools/list -> tools/call`。
- 验收：`tools/list` 返回的 schema 与 `get_all_tools()` 声明逐字段一致。

### P0: 路径白名单没有形成安全边界

`data_dir` 和 `vault_dir` 可以从 MCP 参数传入，当前实现会直接解析路径。作为 agent 工具，这会带来任意路径读写风险。

计划：

- 增加 `knowcran/security.py`，集中实现 `resolve_allowed_data_dir()` 和 `resolve_allowed_vault_dir()`。
- 默认只允许 `KNOWCRAN_DATA_DIR`、`KNOWCRAN_VAULT_DIR` 及其子目录。
- 禁止绝对路径覆盖、`..` 逃逸、软链接逃逸和写到仓库外未授权目录。
- 只读 MCP 模式忽略或拒绝外部传入的 `data_dir`。
- 验收：路径逃逸测试全部失败并返回 LLM 可理解的错误信息。

### P0: 证据溯源链路不完整

`upsert_claim_idempotent()` 已支持新字段，但 `insert_claim()`、`insert_claims()`、部分 agent/LLM extraction 路径仍可能丢失 `citation_key`、`source_quote`、`evidence_status`、`source_span_json`。

计划：

- 将所有 claim 写入统一收敛到 `upsert_claim_idempotent()` 或同等完整字段的 batch upsert。
- 更新 `Claim` model，明确 `source_quote`、`source_span_json`、`evidence_status`、`citation_key` 为一等字段。
- 对 deterministic、single paper、topic batch、agent extraction、LLM extraction 全路径补齐字段传递。
- 对无法提供 quote 的 claim 标记 `evidence_status=metadata_only` 或 `full_text_needed`，不要静默返回空 quote。
- 验收：任意入口写入的 claim 都能在 evidence matrix 中看到 citation key 和 quote/status。

### P1: `read-topic --limit 0` 文档与实现不一致

README 说明 `limit=0` 表示全部可用论文，但实现会传入 SQL `LIMIT 0`，结果为空。

计划：

- 统一 limit 语义：`0` 表示 all available，正数表示上限。
- 在 CLI、MCP handler、storage query 层都处理该语义。
- 对 MCP 增加合理硬上限，例如默认 20、最大 500，避免 agent 一次拉爆上下文。
- 验收：`read-topic --limit 0` 和 `knowcran_read_topic(limit=0)` 返回已有 topic papers 的 claims。

### P1: `discover` 已完成查询返回空结果

当 discovery query 已完成且不 force 时，当前逻辑可能返回 `[]`，MCP 调用方会误以为没有论文。

计划：

- 已完成查询应返回已有 topic papers 的摘要，或返回结构化状态 `skipped=true`、`existing_count`、`papers_preview`。
- 对 partial、failed、retry_scheduled 状态返回明确 next action。
- 支持 cursor/resume 的真实恢复语义，不能只记录 cursor 不使用。
- 验收：重复 discover 同一 topic 时，MCP 返回可解释的已有结果，而不是空数组。

### P1: 防幻觉审计仍偏弱

`knowcran_audit_answer` 目前主要检查 citation pattern，尚未真正做 sentence 到 claim 的匹配，也不充分支持 `[@key]` 等常见引用格式。

计划：

- 支持 citation 格式：`[Key2024]`、`[@Key2024]`、`(Author, 2024)`、`Author2024`。
- 对每个回答句子执行 claim matching：exact overlap、token overlap、citation-scoped claim lookup、可选 embedding/LLM judge。
- 输出四类结果：supported、weakly_supported、unsupported、overclaim。
- 对 abstract-only evidence 加入降级规则，禁止 agent 写成 full-text 或 causal certainty。
- 验收：审计测试能识别无引用、错引用、引用存在但内容不支持、动物实验外推到人类、相关性写成因果。

### P1: 综述输出需要从摘要拼接升级为证据控制写作

当前 review 已比早期更像 evidence digest，但 production MCP 需要明确区分事实、证据等级、限制和开放问题，避免 agent 直接把弱证据写成结论。

计划：

- 将 review 拆成两个层次：`evidence_digest` 和 `narrative_review`。
- 默认 MCP 返回 evidence digest，不默认生成强叙事结论。
- narrative review 必须经过 `audit_answer` 或内部 citation validation。
- 引入 claim selection policy：优先 result/method/limitation，控制 abstract_summary 占比。
- 对 open questions 做语义去重、聚类和计数，不输出重复问题列表。
- 验收：review 输出包含 coverage、limitations、evidence status、citation key map、open question clusters。

### P2: 分页、返回大小和上下文预算需要规范

部分工具用 `len(results) == limit` 判断 `has_more`，在刚好等于 limit 时会产生误报。部分工具返回体没有统一 token budget。

计划：

- 所有列表工具采用 `limit + 1` 查询或 total count 判断 `has_more`。
- 所有 MCP 工具支持 `response_format=json|markdown` 和 `detail=compact|standard|full`。
- 默认 compact 返回高信号字段，full 需要显式请求。
- 对 title、abstract、claim_text、source_quote 设置截断策略，并返回 `truncated=true`。
- 验收：分页测试覆盖 0、limit-1、limit、limit+1、offset 越界。

### P2: Bibliography 和 alias 场景仍有边缘不一致

JSON bibliography 从 paper row 读取 `citation_key`，但 citation key 通常是计算值。Obsidian export 解析 topic 后，claims 仍可能使用原始 topic 查询。

计划：

- bibliography JSON 使用 `citation_key(paper)` 统一计算。
- 所有 topic 入口统一调用 `resolve_topic()`，并显式支持 `include_aliases`、`include_parent`、`include_subtopics`。
- Obsidian export、review、evidence matrix、search claims 使用同一 topic resolution helper。
- 验收：alias topic、parent topic、subtopic 的 papers 与 claims 不错位。

## Features To Add

### 1. MCP Profiles

新增三个明确 profile：

- `serve-mcp-readonly`: 只读查询、evidence matrix、bibliography、audit。
- `serve-mcp-curate`: 允许 discover/read/review/export，但需要安全目录和运行日志。
- `serve-mcp-admin`: 允许 migration、repair、dedupe、topic relation 管理，仅本地人工使用。

每个 profile 明确工具清单和风险等级，README 中给 Claude Code、Codex、Claude Desktop 分别提供配置示例。

### 2. Evidence Contract

定义 agent 可依赖的稳定 evidence contract：

- `PaperRef`: `paper_id`、`title`、`year`、`doi`、`pmid`、`url`、`citation_key`。
- `ClaimRef`: `claim_id`、`claim_text`、`evidence_type`、`confidence`、`evidence_status`、`source_quote`、`source_span`。
- `EvidenceMatrix`: topic、coverage、limitations、rows、citation_key_map。
- `AuditReport`: supported、unsupported、invalid_citations、missing_citations、overclaim_risks、recommended_revision。

### 3. Run Ledger And Observability

把 agent 可变操作写入 run ledger：

- discovery run: query、API params、paper count、timeouts、retries、cursor。
- reading run: paper count、claim count、extraction method、failed papers。
- review run: selected papers、selected claims、audit status。
- export run: vault path、written files、skipped files。

增加 `knowcran_get_runs` 和 `knowcran_get_run` 只读 MCP 工具，方便 agent 解释“刚才做了什么”。

### 4. Reliability Layer For External APIs

Semantic Scholar 调用需要生产化处理：

- connect timeout、read timeout、total timeout 分开配置。
- retry 使用指数退避和 jitter。
- negative cache 记录短期失败，避免 agent 反复撞同一个慢查询。
- rate limit 明确暴露到错误信息，提示 agent 降低 limit 或稍后重试。
- 支持 resumable bulk search，cursor 不能只存不用。

### 5. Quality Gates For Knowledge Output

新增输出前质量门：

- review 生成后自动跑 citation validation。
- narrative answer 必须先拿 evidence matrix，再生成，再 audit。
- 对无 source_quote 的 claim 降权。
- 对 result/method/limitation/open_question 设定最小覆盖要求。
- 对 abstract-only 输出强制添加 limitation。

## Implementation Phases

### Phase 1: MCP Contract And Safety

[ ] Refactor `knowcran/server/mcp.py` so real `tools/list` exposes declared schemas, required fields and annotations.
[ ] Add `knowcran/security.py` path whitelist helpers and reject path escape in every MCP handler.
[ ] Split read-only, curate and admin profiles with explicit tool allowlists.
[ ] Add MCP stdio smoke tests for Claude/Codex style handshake.
[ ] Add documentation examples for Claude Code, Codex and Claude Desktop using readonly by default.

### Phase 2: Evidence Traceability

[ ] Update `Claim` model and storage schema so traceability fields are first-class, not migration-only afterthoughts.
[ ] Replace partial claim insert paths with complete upsert/batch upsert.
[ ] Preserve citation key, quote, source span and evidence status in deterministic, single paper, topic and agent extraction flows.
[ ] Update evidence matrix, bibliography, review and Obsidian export to use one shared topic resolution helper.
[ ] Add migration tests for old databases and new databases.

### Phase 3: Network And Curate Reliability

[ ] Fix `limit=0` semantics across CLI, MCP and storage.
[ ] Fix repeated discover to return existing topic papers or structured skipped status.
[ ] Implement retry ledger with usable `next_retry_at`, negative cache and cursor resume.
[ ] Add per-tool timeout caps and LLM-friendly retry guidance.
[ ] Add tests with mocked ConnectTimeout, ReadTimeout, partial results and repeated runs.

### Phase 4: Anti-Hallucination Layer

[ ] Upgrade `knowcran_audit_answer` from citation pattern checks to citation-scoped claim matching.
[ ] Add support for `[@key]`, `[key]`, `(Author, year)` and paper_id citations.
[ ] Add overclaim detectors for causality, human extrapolation, certainty words and full-text claims from abstract-only evidence.
[ ] Add `knowcran_answer_with_evidence` as an optional workflow tool that retrieves evidence, drafts a constrained answer and audits it.
[ ] Add regression fixtures where the correct behavior is to refuse or qualify unsupported claims.

### Phase 5: Review Quality

[ ] Split review output into evidence digest and narrative review modes.
[ ] Add evidence selection policy that prioritizes result/method/limitation over abstract_summary.
[ ] Deduplicate and cluster open questions.
[ ] Add coverage reporting by evidence type, paper year, study type and abstract-only/full-text-needed status.
[ ] Require audit pass before writing narrative review to vault.

### Phase 6: Packaging And Release

[ ] Update version, README status and MCP docs so they match actual behavior.
[ ] Add `mcp inspect` or local harness instructions for developers.
[ ] Add CI jobs for unit tests, MCP smoke tests and migration tests.
[ ] Add production release checklist with sample Claude Code and Codex configs.
[ ] Tag a `v1.0.0-mcp` release only after all P0/P1 acceptance tests pass.

## Test Matrix

| Area | Required tests |
| --- | --- |
| MCP protocol | initialize, tools/list schema, tools/call success, invalid params, unknown tool |
| Profiles | readonly blocks writes, curate allows approved mutations, admin isolated |
| Security | data_dir escape, vault_dir escape, absolute path override, symlink escape |
| Storage | new DB schema, old DB migration, batch claim upsert, idempotency |
| Topic resolution | exact topic, alias, parent, subtopic, no substring collapse |
| Discovery | first run, repeated run, timeout, retry scheduled, cursor resume |
| Reading | limit 0, per-paper extraction, missing abstract, duplicate claim |
| Evidence | citation key map, source quote fallback, evidence status propagation |
| Audit | missing citation, invalid citation, unsupported claim, overclaim |
| Review | evidence selection, open question dedupe, abstract-only limitation |
| Export | alias topic export, vault whitelist, idempotent file writes |

## Suggested New MCP Tools

- `knowcran_get_runs`: list recent discovery/reading/review/export runs.
- `knowcran_get_run`: inspect one run and its failures.
- `knowcran_get_topic_tree`: return canonical topic, aliases, parent topics and subtopics.
- `knowcran_validate_citations`: validate citation keys without full answer audit.
- `knowcran_answer_with_evidence`: controlled answer workflow that requires evidence retrieval and audit before returning.
- `knowcran_repair_metadata`: admin-only metadata repair using DOI/PMID/Crossref/OpenAlex later.
- `knowcran_dedupe_claims`: admin-only claim duplicate inspection and merge suggestions.

## Rollout Plan

1. Ship `0.6.0` with schema correctness, path whitelist and MCP smoke tests.
2. Ship `0.7.0` with complete evidence traceability and fixed discovery/read semantics.
3. Ship `0.8.0` with upgraded audit and review quality gates.
4. Ship `0.9.0` with run ledger, observability and MCP eval suite.
5. Ship `1.0.0` only after readonly profile can be safely enabled by default in Claude Code/Codex and curate profile has explicit safety controls.

## Open Questions

- 是否要把写操作完全拆成单独 MCP server，而不是同一 server 的不同 profile？
- 是否允许 agent 自动调用 `discover/read-topic`，还是必须要求用户在客户端侧确认？
- 防幻觉审计要保持纯规则匹配，还是引入可选 LLM judge/embedding judge？
