# Mnemosyne Agent LLM Integration Review And Optimization Notes

Review target:

- Repository: `shaoleishen/Mnemosyne`
- Branch inspected: `feat/agent-llm-integration`
- Local checkout inspected: `E:\KNOWCRAN\Mnemosyne-feat-agent-llm-integration`
- Review date: 2026-05-29
- Review mode: static code review. Tests could not be executed in this sandbox because `python.exe` points to the Microsoft Store launcher and `pytest`/`uv` are not available on PATH.

## Executive Summary

This branch has moved in the right direction: agent provider abstraction, audit logging, deterministic fallback, chunked bulk execution, topic membership, and several SQLite indexes are now present. The biggest issue is that the new bulk/parallel executor is mostly not wired into the main user workflows yet.

The current code still has three practical bottlenecks:

1. `discover` still sends one large rerank task to the agent instead of chunking through `BulkExecutor`.
2. `read-topic` still extracts papers serially when an agent provider is enabled.
3. subprocess timeout semantics are wall-clock based, so a long but healthy Claude/Claw/Pi run can be killed even if it is still producing useful progress.

My recommendation: treat this branch as a good foundation, but ask CC to do one more hardening pass before relying on it for large literature runs.

## P0 Findings

### 1. BulkExecutor Exists But Main Workflows Do Not Use It

Files:

- `knowcran/discovery.py:137`
- `knowcran/reading.py:217`
- `knowcran/agents/bulk_executor.py:106`
- `knowcran/agents/bulk_executor.py:183`

Problem:

`BulkExecutor` implements chunking and `ThreadPoolExecutor` based execution, but the real CLI paths do not call it:

- `_agent_rerank()` in `discovery.py` builds one `AgentTask` containing all papers and calls `provider.run(task)` once.
- `read_topic()` loops over papers one by one and calls `extract_paper_claims()` serially.

This means the branch says "bulk parallel execution", but normal commands like:

```bash
knowcran discover "intracerebral hemorrhage" --limit 100 --llm
knowcran read-topic "intracerebral hemorrhage" --limit 100 --llm
```

can still hit huge prompts, long single-task latency, and subprocess timeouts.

Required fix:

- Replace `_agent_rerank()` internals with `BulkExecutor.execute_rerank()`.
- Replace the agent branch of `read_topic()` with `BulkExecutor.execute_extraction()`.
- Preserve deterministic extraction for `--no-llm`.
- Audit each chunk result to `agent_runs`, not only the old one-shot task.
- Print workflow summaries via `format_workflow_summary()` so users can see chunk counts, fallbacks, retries, and timed-out chunks.

Acceptance tests:

- Mock an agent provider and assert `discover(..., agent_provider=provider)` splits 40 papers into multiple rerank tasks.
- Mock slow extraction and assert `read_topic(..., agent_provider=provider)` completes faster with `max_workers > 1` than with `max_workers = 1`.
- Assert returned paper order is stable even when futures complete out of order.
- Assert partial failures do not discard successful chunks.

### 2. Timeout Handling Uses Wall-Clock Timeout, Not "Stuck" Timeout

Files:

- `knowcran/agents/claude_code_provider.py:81`
- `knowcran/agents/claw_provider.py:97`
- `knowcran/agents/pi_print_json_provider.py:171`
- `knowcran/agents/pi_rpc_provider.py:100`
- `knowcran/llm/claw_provider.py:124`

Problem:

The subprocess providers use `subprocess.run(..., timeout=self.timeout_seconds)`. That kills a job after a fixed wall-clock duration. For agentic tools, this is often the wrong timeout model: a task may legitimately run for 20 minutes, but as long as it is still emitting output or heartbeats, it is not stuck.

The user-facing rule should be:

> Do not count a task as timed out just because it is long. Count it as timed out only when it has made no observable progress for an idle timeout window, with a much larger optional hard cap.

Required fix:

- Replace `subprocess.run(timeout=...)` with a shared subprocess runner based on `subprocess.Popen`.
- Stream stdout/stderr incrementally.
- Track `last_activity_at`; reset it whenever stdout/stderr receives bytes or a provider heartbeat is observed.
- Add two separate knobs:
  - `idle_timeout_seconds`: kill only if no output/progress for this long.
  - `hard_timeout_seconds`: optional upper bound, default high or disabled for trusted local agent runs.
- On Windows, kill the process tree, not only the parent process, otherwise child model/tool processes can survive after timeout.
- Return `AgentResult(status="timeout")` for true idle timeout instead of `status="error"`.

Suggested config names:

```text
MNEMOSYNE_AGENT_IDLE_TIMEOUT_SECONDS=300
MNEMOSYNE_AGENT_HARD_TIMEOUT_SECONDS=0
MNEMOSYNE_AGENT_MAX_WORKERS=3
```

Acceptance tests:

- A fake process that emits a line every second for longer than `idle_timeout_seconds` must not time out.
- A fake process that emits nothing for `idle_timeout_seconds` must time out.
- A fake process that exceeds `hard_timeout_seconds` must time out even if it emits output.
- Timeout result status must be exactly `"timeout"`.

### 3. Task Timeout Budgets Are Not Actually Honored By Providers

Files:

- `knowcran/agents/schemas.py:25`
- `knowcran/agents/bulk_executor.py:134`
- `knowcran/agents/bulk_executor.py:208`
- `knowcran/agents/claude_code_provider.py:85`
- `knowcran/agents/claw_provider.py:101`
- `knowcran/agents/pi_print_json_provider.py:176`
- `knowcran/agents/pi_rpc_provider.py:105`

Problem:

`BulkExecutor` sets `AgentTask.timeout_seconds`, but most subprocess providers ignore it and use `self.timeout_seconds` instead. So `ChunkConfig(rerank_timeout=90)` can still run with a provider-level 600 second timeout.

Required fix:

- In each provider, compute an effective timeout from the task:

```python
effective_timeout = task.timeout_seconds or self.timeout_seconds
```

- Once idle timeout is implemented, map task timeout to idle timeout unless a task explicitly asks for a hard cap.
- Avoid double retry multiplication. Right now provider retries and `BulkExecutor` retries can multiply attempts. Pick one owner for retries, preferably `BulkExecutor`.

Acceptance tests:

- Build a task with `timeout_seconds=5` and a provider with `timeout_seconds=600`; assert the subprocess runner receives `5`.
- Assert `max_retries=2` at the bulk layer does not become 9 subprocess attempts because of nested provider retries.

### 4. SQLite Writes Commit Per Row And Will Become A Bottleneck

Files:

- `knowcran/storage.py:212`
- `knowcran/storage.py:251`
- `knowcran/storage.py:345`

Problem:

Bulk methods currently call single-row methods in a loop:

- `upsert_papers()` calls `upsert_paper()` for every paper, and each call commits.
- `insert_claims()` calls `insert_claim()` for every claim, and each call commits.
- `insert_topic_papers()` calls `insert_topic_paper()` for every paper ID, and each call commits.

This is acceptable for tiny tests but slow for real batches. It also makes parallel worker integration more fragile because many small write transactions compete for the same SQLite lock.

Required fix:

- Use one transaction per batch:
  - `with self.conn:`
  - `executemany(...)`
  - commit once
- Keep single-row methods for convenience, but implement batch methods independently instead of looping through single-row commits.
- Add `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, and `PRAGMA busy_timeout=5000` during connection setup.

Acceptance tests:

- Insert 1,000 papers and assert only one transaction path is used in the batch method.
- Re-run `read_topic()` twice and assert claim count remains stable.
- Run a small parallel extraction smoke test against SQLite without `database is locked`.

### 5. SQLite Indexes Are Started But Incomplete For Current Queries

Files:

- `knowcran/storage.py:159`
- `knowcran/storage.py:266`
- `knowcran/storage.py:286`
- `knowcran/storage.py:354`
- `knowcran/storage.py:514`

Problem:

The branch added basic indexes, which is good, but several high-frequency queries still need better coverage:

- Idempotent claim lookup uses `WHERE claim_hash = ? AND paper_id = ? AND topic = ?`.
- Claim review uses `WHERE topic = ? ORDER BY evidence_type, confidence DESC`.
- Topic paper retrieval filters by topic and orders by `COALESCE(tp.llm_relevance_score, tp.relevance_score)`.
- Agent failure/history views filter by `task_type`, `provider`, `status` and order by `created_at`.
- Text search uses `%LIKE%` on `title` and `abstract`, which normal b-tree indexes cannot help.

Required fix:

Add indexes:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_idempotency
ON claims(paper_id, topic, evidence_type, source_location, claim_hash);

CREATE INDEX IF NOT EXISTS idx_claims_topic_type_conf
ON claims(topic, evidence_type, confidence DESC);

CREATE INDEX IF NOT EXISTS idx_topic_papers_topic_score
ON topic_papers(topic, relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_topic_papers_topic_llm_score
ON topic_papers(topic, llm_relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created
ON agent_runs(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_runs_task_provider_status_created
ON agent_runs(task_type, provider, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_runs_task_created
ON llm_runs(task_type, created_at DESC);
```

For `get_papers_by_topic()`, consider SQLite FTS5:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts
USING fts5(paper_id UNINDEXED, title, abstract);
```

Acceptance tests:

- Add `EXPLAIN QUERY PLAN` tests for the important queries and assert they use indexes.
- Add a migration test that opens an old DB and creates all new indexes idempotently.
- Add a performance smoke test with thousands of claims/topic rows.

## P1 Findings

### 6. SQLite Connection Strategy Is Not Ready For Parallel Workers

File:

- `knowcran/storage.py:176`

Problem:

`sqlite3.connect(str(db_path))` uses `check_same_thread=True` by default. If storage writes are moved into worker threads, the shared `Storage` instance will fail. Even if `check_same_thread=False` is used, concurrent writes still need serialization because SQLite allows many readers but one writer.

Required fix:

- Keep DB writes on the main thread after worker results return; or
- Use a write queue; or
- Give each worker its own short-lived `Storage` connection and enable WAL/busy timeout.

Do not share one raw SQLite connection across parallel worker threads without a clear lock/queue policy.

### 7. `max_timeouts` Is Defined But Unused

File:

- `knowcran/agents/bulk_executor.py:32`

Problem:

`ChunkConfig.max_timeouts` exists but there is no circuit breaker. If many chunks hang or fail, the executor continues submitting/processing all tasks.

Required fix:

- Track timeout count across chunks.
- Stop scheduling new chunks when timeout count exceeds `max_timeouts`.
- Mark remaining chunks as `skipped_after_timeout_budget`.
- Surface this in `WorkflowSummary`.

### 8. Fallback Result Is Trusted Even If It Fails

File:

- `knowcran/agents/bulk_executor.py:365`

Problem:

The fallback provider result is returned as `fallback_used` without checking `fallback_result.status == "ok"`. A fallback that returns `error`, `timeout`, or malformed empty output could be reported as success.

Required fix:

- Only return `fallback_used` if fallback status is `"ok"` and output is present.
- Otherwise preserve the primary error and include fallback error in the chunk result.

Acceptance test:

- Primary provider fails, fallback provider returns `status="error"`; summary must not count it as succeeded.

### 9. Long Prompts Are Still Passed Through Argv In Some Providers

Files:

- `knowcran/agents/claude_code_provider.py:80`
- `knowcran/agents/claw_provider.py:76`
- `knowcran/llm/claw_provider.py:124`

Problem:

Large prompts passed as command-line arguments can hit OS command-length limits, especially on Windows. `PiPrintJsonProvider` has a long-prompt path, but it uses `shell=True` for redirection.

Required fix:

- Prefer stdin for all providers that support it.
- If stdin is not supported, use a temporary file argument in a provider-specific, shell-free way.
- Avoid `shell=True` for prompt transport.

## P2 Optimization Suggestions

### Batch Parallelism Policy

Recommended defaults:

- `max_workers=3` for local CLI agents by default.
- `max_workers=1` for rate-limited remote APIs unless an API key tier is configured.
- Separate worker pools for:
  - subprocess agent tasks
  - Semantic Scholar HTTP calls
  - SQLite writes

Do not parallelize Semantic Scholar blindly. The current default `KNOWCRAN_RATE_LIMIT_SECONDS=1.1` means throughput should be improved mainly by reducing request count and using batch endpoints, not by violating the API's rate limits.

### Observability

Add a run summary after each command:

```text
Workflow: extract-12ab34cd
Chunks: 100
Succeeded: 93
Timed out: 2
Fell back: 5
Skipped cache: 0
Avg latency: 18234ms
Provider: claude-code
```

This makes "not stuck, just slow" visible to the user.

### Cache Before Agent Calls

Before submitting an expensive agent chunk:

- Hash task input JSON.
- Check `agent_runs` for a previous successful result with the same `provider`, `task_type`, `input_hash`, and `output_schema_name`.
- Reuse cached parsed output unless `--force` is passed.

This is especially valuable for rerank and extraction, where users often re-run commands while tuning review output.

## Suggested CC Task List

1. Wire `BulkExecutor` into `discover` reranking and `read-topic` extraction.
2. Replace wall-clock subprocess timeout with idle-progress timeout.
3. Make all providers honor `AgentTask.timeout_seconds` or the new task-level timeout budget.
4. Remove nested retry multiplication; keep retries at the bulk executor layer.
5. Batch SQLite writes into one transaction per batch.
6. Add WAL, `busy_timeout`, and the missing indexes.
7. Add a safe SQLite threading policy before writing from parallel workers.
8. Implement `max_timeouts` as a real circuit breaker.
9. Validate fallback provider status before counting fallback as success.
10. Add concurrency, timeout, indexing, and migration tests.

## Verification Checklist

Run after fixes:

```bash
pytest
```

Manual smoke tests:

```bash
knowcran discover "intracerebral hemorrhage" --limit 50 --llm --agent-provider claude-code
knowcran read-topic "intracerebral hemorrhage" --limit 50 --llm --agent-provider claude-code
knowcran review "intracerebral hemorrhage" --llm --agent-provider claude-code
knowcran agents failures --limit 20
knowcran stats
```

Expected behavior:

- Rerank and extraction show chunked workflow summaries.
- A long-running but active agent process is not killed only because wall-clock time passed.
- A silent/stuck process is killed after idle timeout.
- Re-running commands does not duplicate claims.
- SQLite does not report lock errors during parallel extraction.
- `agent_runs` contains chunk-level audit records with status, provider, model, task type, and errors.

