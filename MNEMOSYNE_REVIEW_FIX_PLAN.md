# Mnemosyne Code Review Fix Plan

This document lists the required fixes for the current `shaoleishen/Mnemosyne` MVP implementation. The project has a useful skeleton, but it should still be treated as `v0.1.0-alpha` until the API contracts and evidence scoping issues below are fixed.

## Current Assessment

The repository has the expected MVP shape:

- CLI entrypoint
- Semantic Scholar client
- SQLite storage
- deterministic abstract reading
- Obsidian export
- review generation
- basic tests

However, the current implementation is mostly a happy-path skeleton. The biggest risks are:

1. Some Semantic Scholar API calls do not match the official API contract.
2. Obsidian and review generation mix claims across papers/topics incorrectly.
3. Tests do not cover the real client request shapes, retries, cache behavior, or end-to-end evidence traceability.

Fix these before adding PDF ingestion, LLM extraction, vector search, or Robin-like hypothesis ranking.

## P0: Must Fix Before Next Version

### 1. Fix `SemanticScholarClient.batch_papers()`

File:

```text
knowcran/semantic_scholar.py
```

Current problem:

- The method sends a POST request but discards its response.
- It then sends a GET request to `/graph/v1/paper/batch?fields=...`, which is not the correct API usage.

Required behavior:

- Use `POST https://api.semanticscholar.org/graph/v1/paper/batch`
- Send `fields` as query parameters.
- Send `{"ids": paper_ids}` as JSON body.
- Return the response JSON list.
- Use the same cache, retry, and rate-limit path as other requests.

Expected shape:

```python
def batch_papers(self, paper_ids: list[str], fields: str = DEFAULT_FIELDS) -> list[dict[str, Any]]:
    url = f"{S2_BASE_URL}/graph/v1/paper/batch"
    params = {"fields": fields}
    body = {"ids": paper_ids}
    data = self._post(url, body=body, params=params)
    return data if isinstance(data, list) else []
```

Adjust helper signatures as needed.

Official reference:

- Semantic Scholar Academic Graph API: https://api.semanticscholar.org/api-docs/graph

### 2. Fix `SemanticScholarClient.get_recommendations()`

File:

```text
knowcran/semantic_scholar.py
```

Current problem:

- Multi-seed recommendations are sent to `/recommendations/v1/papers/forpaper`, which is not the correct endpoint.
- `/forpaper/{paper_id}` is for a single positive example paper.

Required behavior:

- For multiple seed papers, use:

```text
POST https://api.semanticscholar.org/recommendations/v1/papers
```

- Query params:

```python
{"limit": limit, "fields": DEFAULT_FIELDS}
```

- JSON body:

```python
{
  "positivePaperIds": seed_paper_ids + (positive_paper_ids or []),
  "negativePaperIds": negative_paper_ids or []
}
```

- Return `recommendedPapers`.
- Use cache, retry, and rate limiting consistently.

Official reference:

- Semantic Scholar Recommendations API: https://api.semanticscholar.org/api-docs/recommendations

### 3. Stop Swallowing Expansion Failures Silently

File:

```text
knowcran/discovery.py
```

Current problem:

- `_expand()` catches exceptions and silently `pass`es.
- This makes failed references/citations/recommendations look like successful empty expansion.

Required behavior:

- Log or print a warning with:
  - paper ID
  - expansion type: `references`, `citations`, or `recommendations`
  - exception message
- Return or print expansion statistics:
  - `expanded_papers`
  - `links`
  - `failed_expansions`

Do not fail the entire discovery run because one paper expansion fails, but do make the failure visible.

### 4. Fix Obsidian Paper Notes Claim Leakage

File:

```text
knowcran/obsidian.py
```

Current problem:

- `export_obsidian()` passes all topic claims into every paper note.
- Every paper note can incorrectly contain claims from unrelated papers.

Required behavior:

When writing each paper note, filter claims by paper:

```python
paper_claims = [c for c in claims if c["paper_id"] == p["paper_id"]]
(papers_dir / filename).write_text(_paper_note(p, paper_claims, links))
```

Add a regression test:

- Seed two papers with distinct claims.
- Export topic.
- Assert each paper note contains only its own claims.

### 5. Fix Review Claim Scoping

File:

```text
knowcran/review.py
```

Current problem:

- `max_papers` limits selected papers, but claims are fetched for the whole topic.
- Evidence matrix and review text can include claims from papers outside the selected paper set.

Required behavior:

- Fetch selected papers first.
- Build `selected_paper_ids`.
- Filter claims to only those paper IDs.

Example:

```python
papers = storage.get_papers_by_topic(topic, limit=max_papers)
selected_paper_ids = {p["paper_id"] for p in papers}
claims = [
    c for c in storage.get_claims_by_topic(topic)
    if c["paper_id"] in selected_paper_ids
]
```

Add a regression test:

- Seed three papers and claims.
- Run `review(topic, max_papers=1)`.
- Assert the evidence matrix only includes claims from the one selected paper.

## P1: Important Reliability Improvements

### 6. Add Real Semantic Scholar Client Contract Tests

Add tests with `httpx.MockTransport` or equivalent. Do not make real network calls.

Required coverage:

- `search_bulk()` sends correct URL and params.
- `search_bulk()` follows pagination token.
- `batch_papers()` sends:
  - method: POST
  - path: `/graph/v1/paper/batch`
  - query param: `fields`
  - JSON body: `{"ids": [...]}`
- `get_recommendations()` sends:
  - method: POST
  - path: `/recommendations/v1/papers`
  - query params: `limit`, `fields`
  - JSON body: `positivePaperIds`, `negativePaperIds`
- `get_recommendations_for_paper()` sends:
  - method: GET
  - path: `/recommendations/v1/papers/forpaper/{paper_id}`
- cache hit returns cached JSON without sending a network request.
- retry happens for `429`, `500`, `502`, `503`, and `504`.

Current tests only check cache key generation, not the actual client behavior.

### 7. Improve Deduplication

Files:

```text
knowcran/discovery.py
knowcran/utils.py
```

Current issue:

- The planned priority was `paperId -> DOI -> PMID -> normalized title`, but the implementation uses `DOI -> PMID -> paperId -> title`.
- More importantly, a single priority key is fragile when different queries return the same paper with different metadata.

Recommended improvement:

- Normalize DOI and PMID.
- Track aliases:
  - `paperId:{id}`
  - `doi:{doi}`
  - `pmid:{pmid}`
  - `title:{normalized_title}`
- Treat records as duplicates if any alias has already been seen.

Add tests for:

- Same DOI with different paper IDs.
- Same PMID with missing DOI.
- Same normalized title with missing external IDs.
- DOI case normalization.

### 8. Make `relevance_score()` Time-Aware

File:

```text
knowcran/utils.py
```

Current issue:

- `current_year = 2026` is hard-coded.

Required behavior:

- Use `datetime.now().year`, or accept `current_year` as an optional parameter for deterministic tests.

Example:

```python
def relevance_score(..., current_year: int | None = None) -> float:
    current_year = current_year or datetime.now().year
```

### 9. Improve Config Testability

File:

```text
knowcran/config.py
```

Current issue:

- Configuration is loaded at import time into module globals.
- This makes tests and multi-vault usage harder.

Recommended improvement:

- Add a `Settings` model or dataclass.
- Keep defaults, but allow CLI/functions to pass:
  - `data_dir`
  - `vault_dir`
  - `rate_limit_seconds`
  - `semantic_scholar_api_key`

Do not over-engineer this yet. A small `Settings.from_env()` is enough.

### 10. Make Evidence Strength Explicit

File:

```text
knowcran/reading.py
```

Current issue:

- Terms like `suggest` and `indicate` are treated similarly to strong results like `significant`.

Recommended improvement:

- Add `evidence_strength` or encode confidence more conservatively.
- Suggested mapping:
  - strong: `significant`, `demonstrate`, `found`, `increased`, `decreased`
  - suggestive: `suggest`, `indicate`, `associated`, `correlate`
  - needs_review: fallback or ambiguous statements

If schema changes are too much for this pass, adjust confidence:

- strong result: `0.75`
- suggestive result: `0.55`
- generated limitation/open question: `0.3-0.5`

## P2: Documentation And Versioning

### 11. Mark The Project As Alpha

Files:

```text
README.md
pyproject.toml
```

Recommended changes:

- Use version `0.1.0-alpha` or state clearly in README that the current release is alpha.
- README should say the current review output is an evidence digest, not a polished narrative review.

### 12. Add GitHub Actions

Create:

```text
.github/workflows/tests.yml
```

Run:

```bash
pip install -e ".[dev]"
pytest
```

Use Python 3.12.

Optional but recommended later:

- Ruff
- mypy
- coverage reporting

### 13. Update README Limitations

Add these limitations:

- API client is rate-limited and cached.
- Abstract-only reading may miss study limitations and full methods.
- Review output is traceable but not yet high-quality academic prose.
- Semantic Scholar metadata can be incomplete; PubMed/Crossref/OpenAlex should be added later for metadata repair.

## Suggested PR Breakdown

Use small PRs or commits:

1. `fix/s2-client-contracts`
   - Fix `batch_papers()`
   - Fix `get_recommendations()`
   - Add client contract tests

2. `fix/evidence-scoping`
   - Fix Obsidian paper-note claim filtering
   - Fix review claim filtering
   - Add regression tests

3. `test/discovery-integration`
   - Add mocked discover -> read-topic -> review test
   - Assert no network calls are made
   - Assert review citations trace to DB papers

4. `docs/alpha-roadmap`
   - Mark alpha status
   - Update README limitations
   - Add roadmap
   - Add GitHub Actions

## Acceptance Criteria

After fixes:

```bash
pip install -e ".[dev]"
knowcran init
knowcran discover "celiac disease" --limit 10
knowcran read-topic "celiac disease" --limit 5
knowcran review "celiac disease"
pytest
```

Expected:

- Tests pass.
- No tests make real network calls.
- `batch_papers()` and recommendations match official Semantic Scholar API contracts.
- Expansion failures are visible.
- Paper notes contain only claims from that paper.
- Reviews and evidence matrices contain only claims from selected papers.
- Every citation or paper ID in review output can be traced back to a row in SQLite.

## Do Not Add Yet

Do not add these before P0/P1 are complete:

- LLM extraction
- PDF full-text ingestion
- vector index
- Robin-style hypothesis ranking
- multi-agent orchestration

The project needs a trustworthy evidence and API foundation first.
