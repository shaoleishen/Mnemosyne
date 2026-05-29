# Mnemosyne Large-Scale Discovery Optimization Plan

Review target:

- Branch inspected: `feat/agent-llm-integration`
- Local checkout inspected: `E:\KNOWCRAN\Mnemosyne-feat-agent-llm-integration`
- Review date: 2026-05-29
- Goal: avoid repeated literature queries and make large-scale discovery resilient to timeout, rate limit, and interruption.

## Bottom Line

The current branch has useful per-run deduplication and local API caching, but it does not yet guarantee "do not query duplicate literature" at scale.

Current behavior:

- A single `discover()` run deduplicates raw papers in memory by S2 paper ID, DOI, PMID, and normalized title.
- The HTTP cache avoids repeating exactly identical API requests.
- SQLite `papers.paper_id` prevents duplicate S2 paper IDs.

Missing behavior:

- No persistent query ledger, so the system cannot know that a topic/query has already been fully attempted.
- No checkpoint/resume state for paginated API calls.
- No failed-query cooldown, so timed-out requests can be retried repeatedly.
- No paper alias table, so the database can still store semantically identical papers if S2 returns different IDs for the same DOI/title.
- No coverage-aware topic logic, so repeated manual variants like `ICH stroke`, `hemorrhagic stroke`, and `intracerebral hemorrhage treatment` can keep refetching overlapping literature.
- Network timeouts are not caught and persisted as resumable failures.

The fix should not be "just increase timeout". The robust fix is a resumable discovery scheduler with query fingerprints, paper identity aliases, adaptive backoff, and batch database writes.

## Target Contract

After the optimization pass, these should be true:

1. Running the same discover command twice should perform zero network calls unless `--refresh` or `--force` is passed.
2. Running a related alias query should reuse the canonical topic and skip already completed query fingerprints.
3. A timeout should mark only the current request/page as failed or retryable; it should not lose the whole run.
4. A later `--resume` should continue from the last cursor/token/page, not restart from the beginning.
5. Papers should be deduplicated across runs by DOI, PMID, arXiv ID, S2 paper ID, and normalized title hash.
6. SQLite should remain responsive with tens or hundreds of thousands of papers.

## P0: Add A Persistent Query Ledger

Files to change:

- `knowcran/storage.py`
- `knowcran/discovery.py`
- `knowcran/semantic_scholar.py`
- `knowcran/cli.py`

Add a table that records every planned query and its state:

```sql
CREATE TABLE IF NOT EXISTS discovery_queries (
    query_id TEXT PRIMARY KEY,
    canonical_topic TEXT NOT NULL,
    raw_query TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    cursor_token TEXT,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    paper_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TEXT,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(canonical_topic, query_hash, api_endpoint, params_hash)
);

CREATE INDEX IF NOT EXISTS idx_discovery_queries_topic_status
ON discovery_queries(canonical_topic, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_discovery_queries_retry
ON discovery_queries(status, next_retry_at);
```

Query statuses:

```text
planned
running
partial
completed
failed_retryable
failed_permanent
skipped_duplicate
```

Required behavior:

- Before any network call, compute a stable query fingerprint.
- If the same `(canonical_topic, query_hash, endpoint, params_hash)` is already `completed`, skip it.
- If it is `partial`, resume from `cursor_token`.
- If it is `failed_retryable`, retry only after `next_retry_at`.
- If `--force` is passed, ignore the completed state but still reuse cache where possible.

Acceptance tests:

- Run `discover("intracerebral hemorrhage", limit=200)` twice with a mocked client; the second run should not call the client.
- Simulate one page success then timeout; assert the ledger stores `partial` and the cursor token.
- Run with `--resume`; assert it starts from the saved cursor token.

## P0: Add Cross-Run Paper Identity Deduplication

Files to change:

- `knowcran/storage.py`
- `knowcran/models.py`
- `knowcran/discovery.py`

Current `papers.paper_id` uniqueness is not enough. Add an alias table:

```sql
CREATE TABLE IF NOT EXISTS paper_aliases (
    alias_type TEXT NOT NULL,
    alias_value TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(alias_type, alias_value)
);

CREATE INDEX IF NOT EXISTS idx_paper_aliases_paper_id
ON paper_aliases(paper_id);
```

Alias types:

```text
s2
doi
pmid
arxiv
title_hash
title_year_hash
```

Normalization rules:

- DOI: lowercase, strip URL prefixes, strip leading `doi:`.
- PMID: digits only.
- arXiv: lowercase, strip version suffix if appropriate.
- title hash: lowercase, remove punctuation, collapse whitespace.
- title-year hash: same normalized title plus year, useful when DOI/PMID are missing.

Required behavior:

- Before inserting a paper, derive all aliases.
- If any alias already exists, merge into the canonical `paper_id` instead of inserting a duplicate row.
- Insert any new aliases for the canonical paper.
- Track duplicate merges in a lightweight audit table or return count in discovery summary.

Acceptance tests:

- Two records with different S2 IDs but same DOI result in one paper row and two `s2` aliases.
- Two records with missing DOI but same normalized title/year result in one canonical paper.
- A repeated discover run does not increase paper count for already known literature.

## P0: Make Semantic Scholar Requests Resumable And Timeout-Safe

Files to change:

- `knowcran/semantic_scholar.py`
- `knowcran/discovery.py`

Current issue:

- `httpx.Client(timeout=30.0)` is too blunt.
- `_get()` and `_post()` retry only HTTP status codes. They do not catch `httpx.TimeoutException`, `httpx.ConnectError`, or `httpx.TransportError`.
- Failed requests are not persisted as retryable work.

Required client changes:

```python
timeout = httpx.Timeout(
    connect=30.0,
    read=120.0,
    write=30.0,
    pool=30.0,
)
```

Add retry handling for:

```python
httpx.TimeoutException
httpx.ConnectError
httpx.NetworkError
httpx.TransportError
```

Backoff rules:

- Honor `Retry-After` on 429 if present.
- Otherwise use exponential backoff with jitter.
- Use a max retry count per request, for example 5.
- After max retries, store request/page as `failed_retryable` with `next_retry_at`.
- Do not crash the whole discovery workflow when one query/page fails.

Important distinction:

- A network request can time out.
- A discovery run should not be lost because of that timeout.

The system should return a partial summary:

```text
Completed queries: 42
Partial queries: 3
Retryable failures: 5
New papers: 4900
Duplicate papers skipped: 1800
Resume command: knowcran discover "intracerebral hemorrhage" --resume
```

Acceptance tests:

- Mock `ReadTimeout` on page 2; page 1 results remain stored and query status becomes `partial` or `failed_retryable`.
- Mock 429 with `Retry-After`; assert retry sleep uses that value.
- Mock repeated transport errors; assert query state is persisted and next run can resume.

## P0: Add Coverage-Aware Topic Skipping

Files to change:

- `knowcran/discovery.py`
- `knowcran/storage.py`
- `knowcran/cli.py`

Current issue:

Manual repeated commands can keep querying overlapping literature:

```bash
knowcran discover "intracerebral hemorrhage" --limit 200
knowcran discover "ICH stroke" --limit 200
knowcran discover "hemorrhagic stroke" --limit 200
knowcran discover "intracerebral hemorrhage treatment" --limit 200
```

Some are legitimate subtopics; some are aliases; some overlap heavily.

Required behavior:

- Normalize known aliases to a canonical topic before planning queries.
- Use `topic_aliases` aggressively:
  - `ICH` -> `intracerebral hemorrhage`
  - `intracerebral haemorrhage` -> `intracerebral hemorrhage`
  - user-added aliases via CLI: `knowcran topics alias add "ICH stroke" "intracerebral hemorrhage"`
- Before running, estimate local coverage:
  - existing topic paper count
  - completed query fingerprints
  - last refreshed timestamp
  - known subtopics already covered

Suggested CLI flags:

```bash
knowcran discover "intracerebral hemorrhage" --limit 200 --resume
knowcran discover "intracerebral hemorrhage" --limit 200 --refresh-after 30d
knowcran discover "intracerebral hemorrhage" --limit 200 --force
knowcran topics alias add "ICH stroke" "intracerebral hemorrhage"
knowcran topics coverage "intracerebral hemorrhage"
```

Skip logic:

- If topic has at least `limit` papers and all planned query fingerprints are completed, skip network calls.
- If topic is stale by `--refresh-after`, run only refresh queries.
- If user asks for a true subtopic like `ferroptosis intracerebral hemorrhage`, store it as a subtopic but still dedup papers globally.

Acceptance tests:

- Alias query maps to canonical topic and does not repeat completed canonical query fingerprints.
- True subtopic runs new query fingerprints but does not duplicate existing papers.
- `--force` bypasses query ledger but still deduplicates papers on insert.

## P1: Query Plan Deduplication Before Network Calls

Files to change:

- `knowcran/utils.py`
- `knowcran/discovery.py`

Current `generate_queries()` returns only five strings, but user workflows often run many manually generated variants. Add a query planning stage:

```python
def normalize_query(q: str) -> str:
    ...

def query_fingerprint(q: str, endpoint: str, fields: str, limit: int) -> str:
    ...

def plan_discovery_queries(topic: str, variants: list[str]) -> list[DiscoveryQuery]:
    ...
```

Dedup rules:

- Lowercase.
- Normalize British/American spelling where relevant.
- Collapse punctuation and whitespace.
- Map known abbreviations.
- Remove duplicate modifiers: `surgery` vs `surgical` can share a stem in the query fingerprint, but keep raw query text for audit.
- Sort unordered modifier tokens for generated query variants when order does not matter.

Do not over-dedup:

- `intracerebral hemorrhage treatment`
- `intracerebral hemorrhage surgery`
- `intracerebral hemorrhage anticoagulation reversal`

These are different intents and should remain distinct query fingerprints unless the user explicitly aliases them.

Acceptance tests:

- `ICH`, `ich`, and `intracerebral haemorrhage` can resolve to the same canonical topic.
- Duplicate generated query strings collapse before network calls.
- Different subtopics do not collapse accidentally.

## P1: Separate Fetch, Normalize, Store, And Rank Phases

Large-scale discovery should run as a pipeline:

```text
Query planner
  -> fetch pages with checkpoint
  -> normalize paper identity
  -> batch upsert papers and aliases
  -> update topic_papers
  -> rank from local DB
  -> optional agent rerank in chunks
```

This avoids the current pattern where the run gathers all raw papers first and only then writes. For thousands of papers, write incrementally after each page or each small batch.

Recommended batch size:

- API page/batch: whatever the endpoint returns safely.
- DB write batch: 100 to 500 papers.
- Agent rerank chunk: 10 to 20 papers.
- Claim extraction chunk: 1 paper per task, 2 to 4 workers.

Acceptance tests:

- Kill the process after first batch; restart with `--resume`; already written papers are not fetched again.
- Memory usage should not grow with total corpus size.

## P1: Make SQLite Ready For Large Data

Files to change:

- `knowcran/storage.py`

Add connection pragmas:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=10000;
PRAGMA foreign_keys=ON;
```

Batch write methods should commit once per batch, not once per row.

Indexes to add:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_idempotency
ON claims(paper_id, topic, evidence_type, source_location, claim_hash);

CREATE INDEX IF NOT EXISTS idx_topic_papers_topic_score
ON topic_papers(topic, relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_paper_aliases_type_value
ON paper_aliases(alias_type, alias_value);

CREATE INDEX IF NOT EXISTS idx_discovery_queries_topic_hash
ON discovery_queries(canonical_topic, query_hash);
```

For local text search, use FTS5 instead of `%LIKE%`:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts
USING fts5(paper_id UNINDEXED, title, abstract);
```

Acceptance tests:

- Insert 100,000 mocked papers and query topic papers within an acceptable threshold.
- `EXPLAIN QUERY PLAN` confirms index use for query ledger and paper alias lookup.

## P1: Replace "Timeout Means Failed Run" With "Timeout Means Retryable Work Item"

For network discovery:

- Timeout on one API call should not abort the whole topic.
- Store the failing query/page as retryable.
- Continue with other planned queries if rate limit policy allows.

For agent subprocesses:

- Use idle-progress timeout rather than wall-clock timeout.
- Large but active tasks are allowed to continue.
- Silent tasks are killed and converted into retryable/fallback chunk failures.

Suggested status model:

```text
completed
partial
retryable_timeout
retryable_rate_limited
retryable_network
permanent_bad_request
skipped_duplicate
```

## P2: Recommended CLI UX

Add commands:

```bash
knowcran discover "intracerebral hemorrhage" --limit 200 --resume
knowcran discover "intracerebral hemorrhage" --limit 200 --refresh-after 30d
knowcran discover "intracerebral hemorrhage" --limit 200 --dry-run
knowcran discovery status "intracerebral hemorrhage"
knowcran discovery retry-failed "intracerebral hemorrhage"
knowcran topics coverage "intracerebral hemorrhage"
```

`--dry-run` should show:

```text
Canonical topic: intracerebral hemorrhage
Planned query fingerprints: 5
Already completed: 4
Will fetch: 1
Known papers for topic: 5261
Estimated duplicate skip: high
```

This prevents accidental repeat harvesting.

## P2: Better Summaries For Large Runs

Every discovery run should print:

```text
Topic: intracerebral hemorrhage
Canonical topic: intracerebral hemorrhage
Queries planned: 50
Queries skipped as already complete: 37
Queries fetched: 8
Queries partial/retryable: 5
Raw papers received: 4900
Canonical new papers: 612
Duplicate papers merged/skipped: 4288
Network retries: 22
429 waits: 6
Timeouts persisted for resume: 5
```

This makes it obvious whether the system is discovering new literature or repeatedly walking the same ground.

## Better CC Task List

Ask CC to implement in this order:

1. Add `discovery_queries` ledger with query fingerprint, status, cursor token, attempts, and retry metadata.
2. Add `paper_aliases` and canonical paper merge logic.
3. Add `--resume`, `--force`, and `--dry-run` to `discover`.
4. Make Semantic Scholar client use explicit connect/read/write/pool timeouts.
5. Catch timeout/network exceptions and persist them as retryable query states.
6. Honor `Retry-After`; otherwise use exponential backoff with jitter.
7. Skip completed query fingerprints before network calls.
8. Add topic alias/coverage logic so repeated alias queries do not refetch the same corpus.
9. Batch SQLite writes and enable WAL/busy timeout.
10. Add FTS5 or another indexed local search path for already stored papers.
11. Add large mocked-corpus tests and resume-after-timeout tests.

## Verification Scenarios

### Same Command Twice

```bash
knowcran discover "intracerebral hemorrhage" --limit 200 --no-llm
knowcran discover "intracerebral hemorrhage" --limit 200 --no-llm
```

Expected:

- Second run does zero network calls.
- Paper count does not increase.
- Summary says planned queries were skipped as already completed.

### Timeout Mid-Run

Mock page 2 to raise `ReadTimeout`.

Expected:

- Page 1 papers are stored.
- Query status is `partial` or `failed_retryable`.
- `--resume` continues from the saved token or next planned page.

### Alias Query

```bash
knowcran topics alias add "ICH stroke" "intracerebral hemorrhage"
knowcran discover "ICH stroke" --limit 200 --no-llm
```

Expected:

- Canonical topic resolves to `intracerebral hemorrhage`.
- Completed canonical query fingerprints are skipped.
- No duplicate papers are inserted.

### Duplicate Paper Identity

Mock two papers:

- S2 ID A, DOI `10.1000/ABC`
- S2 ID B, DOI `https://doi.org/10.1000/abc`

Expected:

- One canonical paper row.
- Two `s2` aliases.
- One normalized DOI alias.

### Large Corpus

Mock 100,000 paper records.

Expected:

- Batch inserts complete without per-row commits.
- Topic lookup uses indexes.
- Memory usage remains bounded by batch size.

