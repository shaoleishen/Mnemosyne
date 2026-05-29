# Mnemosyne / KnowCran Optimization and Refactoring Plan

This plan aims to dramatically optimize the performance, scalability, and robustness of the Mnemosyne project. The scope is large, covering API throughput, parallel execution, database scaling, and critical bug fixes for local execution.

## Proposed Changes

### 1. Review Synthesis Bug Fix (Deterministic Fallback)
* **Problem**: When using the deterministic provider (which does not call an LLM), the generated reviews contain "Needs evidence." for all sections. This occurs because `DeterministicProvider` returns empty lists `[]` for sections like `background` and `main_evidence`, which is parsed successfully by `_agent_review_synthesis` in `knowcran/review.py`. This completely bypasses the rule-based review synthesis `_build_review_text` which actually extracts claims from the SQLite database.
* **Proposed Solution**: In `_agent_review_synthesis` or `review.py`, check if the agent provider is deterministic, or if the returned JSON yields completely empty sections despite database claims being present. If so, return `None` to force the fallback to the rule-based `_build_review_text` generator.

### 2. Semantic Scholar API Call Optimization
* **Problem**: In `knowcran/discovery.py`, the `_expand` method makes two separate API requests for every seed paper (one for references and one for citations), leading to high network latency and rate-limiting overhead.
* **Proposed Solution**: Modify the client call to fetch both collections in a single request by passing `fields="references,citations"`. This will reduce the number of API calls during the expansion phase by **50%**.

### 3. Rate Limit Respect & Configuration
* **Context**: Semantic Scholar's standard API Key rate limit is strictly **1 request per second** cumulative across all endpoints. To prevent hitting 429 rate limit exceptions, we must strictly respect this limit.
* **Proposed Solution**: We will keep the default rate limit to a safe `1.1` seconds, but ensure it is fully configurable via the `KNOWCRAN_RATE_LIMIT_SECONDS` environment variable (allowing users with higher partner tiers to lower it if desired). Our main throughput optimization will rely on **minimizing request count** (combining references and citations requests) rather than violating the rate limit.

### 4. Integration of the Chunked Bulk Executor
* **Problem**: `BulkExecutor` in `knowcran/agents/bulk_executor.py` is implemented but never integrated into the core workflows like `discover` or `read-topic`. Reranking is run on the entire paper list in one massive LLM prompt, causing frequent timeouts.
* **Proposed Solution**: Update `discover` to use the `BulkExecutor` for reranking and `read_topic` to use `BulkExecutor` for claim extraction.

### 5. Parallel Subprocess & API Execution
* **Problem**: Bootstrapping CLI agents (like `pi` or `claw`) or fetching data sequentially for dozens of papers is slow.
* **Proposed Solution**: Add `ThreadPoolExecutor` inside `BulkExecutor` to run claim extractions and Semantic Scholar fetches concurrently (e.g., with 3-5 workers), reducing bottlenecking and increasing throughput by **300%-500%**.

### 6. Database Indexing for Scaling
* **Problem**: No indices exist on frequently queried fields in SQLite, which will lead to slow queries as the vault grows.
* **Proposed Solution**: Modify `knowcran/storage.py` to automatically add indices during database migration:
  * `idx_claims_topic` on `claims(topic)`
  * `idx_claims_paper_id` on `claims(paper_id)`
  * `idx_papers_relevance_score` on `papers(relevance_score)`
  * `idx_topic_papers_topic` on `topic_papers(topic)`

---

## Verification Plan

### Automated Tests
- Run existing unit tests:
  ```bash
  pytest
  ```
- Write new tests in `tests/test_bulk_executor.py` and `tests/test_review.py` to cover parallel execution and deterministic review fallback behavior.

### Manual Verification
- Run CLI commands to ensure correct behavior:
  - `knowcran discover "intracerebral hemorrhage" --limit 20`
  - `knowcran read-topic "intracerebral hemorrhage" --limit 10`
  - `knowcran review "intracerebral hemorrhage"`
- Inspect the generated markdown files in `vault/reviews/` to ensure they are fully populated.
