# Mnemosyne Second Review Fix Plan

Review target:

- Repository: `shaoleishen/Mnemosyne`
- Branch inspected: `main`
- Review date: 2026-05-27

## Current Assessment

The second implementation round fixed several important issues from the previous review:

- Project is now clearly marked as `v0.1.0-alpha`.
- `batch_papers()` now uses the correct `POST /graph/v1/paper/batch` shape.
- Review claim scoping now filters claims to selected papers.
- Obsidian paper notes now filter claims by `paper_id`.
- Expansion failures are visible instead of silently swallowed.
- Deduplication now uses alias sets rather than a single priority key.
- GitHub Actions was added.

This is real progress. The project is now closer to a credible alpha. However, it still needs another pass before adding PDF ingestion, LLM extraction, vector search, or Robin-like hypothesis generation.

The main remaining problems are:

1. Semantic Scholar client contract tests appear to be missing or incomplete.
2. `get_recommendations()` still bypasses the unified cache/retry helper.
3. Obsidian links from claim notes to paper notes are currently broken or weak.
4. Review output uses paper IDs instead of stable citation keys.
5. `read-paper` claims are hard to reuse in topic reviews because they are stored under the paper title as topic.

## P0: Must Fix Next

### 1. Add Real Semantic Scholar Client Contract Tests

Files:

```text
knowcran/semantic_scholar.py
tests/test_semantic_scholar_client.py
```

Problem:

- The repository now has better unit tests for dedup, review, and Obsidian scoping.
- But there does not appear to be a real `httpx.MockTransport`-based client contract test file.
- This means the API client can still drift from Semantic Scholar's real request shape while tests stay green.

Required tests:

- `search_bulk()` sends:
  - `GET /graph/v1/paper/search/bulk`
  - query params: `query`, `fields`
- `search_bulk()` follows `token` pagination and respects final `limit`.
- `batch_papers()` sends:
  - `POST /graph/v1/paper/batch`
  - query param: `fields`
  - JSON body: `{"ids": [...]}`
- `get_paper()` sends:
  - `GET /graph/v1/paper/{paper_id}`
  - query param: `fields`
- `get_recommendations()` sends:
  - `POST /recommendations/v1/papers`
  - query params: `limit`, `fields`
  - JSON body: `positivePaperIds`, `negativePaperIds`
- `get_recommendations_for_paper()` sends:
  - `GET /recommendations/v1/papers/forpaper/{paper_id}`
- cache hit returns cached JSON without sending a network request.
- retries happen for `429`, `500`, `502`, `503`, and `504`.

Implementation note:

- Make `SemanticScholarClient` accept an optional injected `httpx.Client` or `transport`.
- Do not monkeypatch private internals unless unavoidable.

Example direction:

```python
class SemanticScholarClient:
    def __init__(
        self,
        api_key: str = S2_API_KEY,
        rate_limit: float = RATE_LIMIT_SECONDS,
        raw_dir: Path = RAW_DIR,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
```

Official references:

- Academic Graph API: https://api.semanticscholar.org/api-docs/graph
- Recommendations API: https://api.semanticscholar.org/api-docs/recommendations

### 2. Route `get_recommendations()` Through `_post()`

File:

```text
knowcran/semantic_scholar.py
```

Problem:

- `batch_papers()` now uses `_post()`, so it gets cache/retry/rate-limit behavior.
- `get_recommendations()` still manually calls `self._client.post(...)`.
- This bypasses raw JSON cache and creates inconsistent request behavior.

Required behavior:

Use `_post()` for recommendations:

```python
def get_recommendations(...):
    url = f"{S2_BASE_URL}/recommendations/v1/papers"
    body = {
        "positivePaperIds": seed_paper_ids + (positive_paper_ids or []),
        "negativePaperIds": negative_paper_ids or [],
    }
    params = {"limit": limit, "fields": DEFAULT_FIELDS}
    data = self._post(url, body=body, params=params)
    return data.get("recommendedPapers", []) if isinstance(data, dict) else []
```

Add a test proving the second call is served from cache.

### 3. Fix Obsidian Claim-to-Paper Links

File:

```text
knowcran/obsidian.py
```

Problem:

- Claim notes currently link to:

```markdown
[[paper_id]]
```

- Paper note filenames are:

```text
{year}_{slug_title}.md
```

- This means claim note links do not reliably resolve in Obsidian.

Required behavior:

Use the actual paper note basename as the Obsidian target.

Recommended helper:

```python
def paper_note_stem(paper: dict[str, Any]) -> str:
    return f"{paper.get('year', 'unknown')}_{slugify(paper['title'])}"
```

Then either:

- Pass a `paper_id -> note_stem` map into `_claim_note()`, or
- Add paper title/note target when fetching claims for export.

Expected claim note source:

```markdown
**Source**: [[2023_celiac-disease-a-review|Celiac Disease: A Review]]
```

Add a test:

- Export one paper and one claim.
- Assert claim note contains the actual paper note stem, not only the raw paper ID.

### 4. Use Stable Citation Keys In Review Output

File:

```text
knowcran/review.py
knowcran/bibtex.py
```

Problem:

- Review evidence currently cites `(Paper: {paper_id})`.
- BibTeX keys are generated from `slugify(paper_id)`.
- The review does not expose the same key used in the bibliography.

Required behavior:

- Create a shared citation key helper, for example:

```python
def citation_key(paper: dict[str, Any]) -> str:
    # Suggested shape: first author + year + short title, fallback to paper_id.
```

- Use that helper in both:
  - review inline evidence bullets
  - BibTeX entries

Example output:

```markdown
- Gluten-free diet improved symptoms in the studied cohort [@smith2023celiac].
```

BibTeX:

```bibtex
@article{smith2023celiac,
  ...
}
```

Add tests:

- Every `[@key]` in review text exists in generated bibliography.
- Every evidence matrix row can still trace back to a DB `paper_id`.

### 5. Make `read-paper` Compatible With Topic Reviews

File:

```text
knowcran/reading.py
knowcran/cli.py
```

Problem:

- `read_topic("celiac disease")` stores claims with topic `celiac disease`.
- `read_paper(paper_id)` stores claims with topic equal to the paper title.
- If a user manually reads a paper and then runs `review("celiac disease")`, that paper's claims may not appear.

Required behavior:

Allow `read-paper` to accept an optional topic:

```bash
knowcran read-paper PAPER_ID --topic "celiac disease"
```

Implementation:

```python
def read_paper(paper_id: str, topic: str | None = None, storage: Storage | None = None) -> list[Claim]:
    ...
    topic = topic or paper.get("title", "")
```

Add tests:

- Read paper with `topic="celiac disease"`.
- Run review for `celiac disease`.
- Assert that paper's claims appear in the evidence matrix.

## P1: Important Design Improvements

### 6. Decide Whether `discover --limit` Means Total Or Per Query

Files:

```text
knowcran/cli.py
knowcran/discovery.py
README.md
```

Current behavior:

- `discover(question, limit=10)` runs five generated queries.
- Each query can return up to 10 papers.
- Result can be up to 50 raw papers before deduplication.

This is not necessarily wrong, but it should be explicit.

Pick one:

Option A: Make `limit` total.

- Distribute limit across generated queries.
- Example: `limit=50`, 5 queries means roughly 10 per query.

Option B: Keep current behavior but rename/help text.

- CLI help should say: `Max papers per generated query`.
- README should warn that total raw requests may be `limit * number_of_queries`.

Recommendation:

- For a local, rate-limited tool, make `limit` total.

### 7. Use Full Metadata Fetch For Expansion Papers

File:

```text
knowcran/discovery.py
```

Current behavior:

- Expansion gets `references` and `citations` directly from `get_paper(..., fields="references")` and `fields="citations"`.
- The nested objects may not contain the same full metadata fields as search results.

Recommended behavior:

1. Fetch references/citations for link IDs.
2. Collect target paper IDs.
3. Call `batch_papers()` with `DEFAULT_FIELDS`.
4. Store complete `PaperRecord`s for expanded papers.

This will make expansion metadata more reliable and keep `PaperRecord.from_s2()` assumptions cleaner.

### 8. Make Settings Actually Flow Through The App

File:

```text
knowcran/config.py
knowcran/cli.py
knowcran/storage.py
knowcran/semantic_scholar.py
```

Current state:

- A `Settings` dataclass now exists.
- But most modules still rely on module-level defaults captured at import time.

Recommended next step:

- Keep backward-compatible defaults.
- Add optional CLI options:

```bash
knowcran --data-dir data --vault-dir vault ...
```

or per-command options if Typer global options are inconvenient.

- Pass explicit paths to:
  - `Storage(db_path=settings.db_path)`
  - `SemanticScholarClient(raw_dir=settings.raw_dir, rate_limit=settings.rate_limit_seconds, api_key=settings.s2_api_key)`
  - Obsidian/review export `vault_dir=settings.vault_dir`

Do this before more features depend on config.

### 9. Improve Review Naming And Branding

Files:

```text
README.md
pyproject.toml
knowcran/cli.py
```

Current mismatch:

- Repository/project name: `Mnemosyne`
- Python package and CLI: `knowcran`

This can be okay during early development, but it will become confusing.

Options:

- Keep package `knowcran`, but expose CLI aliases:

```toml
[project.scripts]
knowcran = "knowcran.cli:app"
mnemosyne = "knowcran.cli:app"
```

- Or rename package later once APIs stabilize.

Recommendation:

- Add `mnemosyne` CLI alias now.
- Avoid package rename until after alpha.

### 10. Add A Mocked End-To-End Test

Create:

```text
tests/test_mvp_flow.py
```

Test flow:

1. Use a mock Semantic Scholar client.
2. Run `discover("celiac disease", limit=5)`.
3. Run `read_topic("celiac disease")`.
4. Run `export_obsidian("celiac disease")`.
5. Run `review("celiac disease")`.

Assertions:

- Papers are stored.
- Claims are stored.
- Paper note exists.
- Review exists.
- Evidence matrix rows all map to selected DB papers.
- No real network calls are made.

## P2: Later, But Worth Tracking

### 11. Add Foreign Keys And Basic Integrity Checks

File:

```text
knowcran/storage.py
```

Recommended:

- Enable `PRAGMA foreign_keys = ON`.
- Add foreign key relationship from `claims.paper_id` to `papers.paper_id`.
- Add relationship for `paper_links.source_paper_id`.

This may require small migration handling if existing local DBs exist.

### 12. Add Metadata Repair Sources Later

Not for this PR, but roadmap should include:

- PubMed for PMID/MeSH/abstract repair.
- Crossref for DOI metadata repair.
- OpenAlex for open citation and institution metadata.

Do not add this before the current Semantic Scholar client is fully tested.

### 13. Keep LLM/PDF/Vector Work Blocked Until Foundation Is Stable

Do not add yet:

- LLM claim extraction
- PDF full-text ingestion
- vector index
- multi-agent orchestration
- Robin-like hypothesis ranking

The evidence foundation should be boring and trustworthy first.

## Suggested PR Breakdown

### PR 1: `fix/s2-client-contract-tests`

Scope:

- Injectable `httpx.Client` or `transport`.
- `tests/test_semantic_scholar_client.py`.
- Route recommendations through `_post()`.
- Cache-hit and retry tests.

Acceptance:

- No real network calls in tests.
- Tests prove exact method/path/params/body for all client methods.

### PR 2: `fix/obsidian-review-links`

Scope:

- Stable paper note stem helper.
- Claim notes link to actual paper note.
- Shared citation key helper.
- Review inline citations use `[@key]`.
- BibTeX uses the same keys.

Acceptance:

- Claim note links resolve to exported paper note stems.
- Every `[@key]` in review text exists in bibliography.

### PR 3: `fix/topic-flow-and-limit`

Scope:

- `read-paper --topic`.
- Decide total vs per-query `discover --limit`.
- Update README/CLI help.

Acceptance:

- Claims created by `read-paper --topic X` appear in `review X`.
- `discover --limit` behavior is explicit and tested.

### PR 4: `test/mvp-flow`

Scope:

- Add mocked end-to-end MVP test.
- Verify discover -> read-topic -> export-obsidian -> review.

Acceptance:

- The test validates the user-facing alpha workflow without network access.

## Final Acceptance Criteria For Next Review

Run:

```bash
pip install -e ".[dev]"
pytest
knowcran init
knowcran discover "celiac disease" --limit 10
knowcran read-topic "celiac disease" --limit 5
knowcran review "celiac disease"
```

Expected:

- Tests pass in GitHub Actions.
- No tests call the real Semantic Scholar network.
- All Semantic Scholar client methods have contract tests.
- Recommendations use the same cache/retry/rate-limit pathway as other POST requests.
- Obsidian claim notes link to actual paper notes.
- Review citations use stable keys that match BibTeX entries.
- `read-paper --topic` works and feeds topic reviews.
- `discover --limit` semantics are documented and tested.

