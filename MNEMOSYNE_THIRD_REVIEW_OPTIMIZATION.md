# Mnemosyne Third Review And Optimization Notes

Review target:

- Repository: `shaoleishen/Mnemosyne`
- Branch inspected: `main`
- Local run artifact inspected: `E:\KNOWCRAN\knowtest`
- Review date: 2026-05-27

## Executive Summary

This round is a real improvement over the previous review. Several earlier issues appear fixed:

- `discover --limit` is now treated as a total limit instead of per generated query.
- `get_recommendations()` now goes through the shared `_post()` cache/retry/rate-limit helper.
- `read-paper` supports `--topic`.
- Obsidian claim notes now link to exported paper-note stems instead of raw `paper_id`.
- Review citations now use citation keys that match bibliography keys.
- A `mnemosyne` CLI alias and a mocked MVP flow test were added.

However, the local intracerebral hemorrhage test shows the system is still not ready for PDF ingestion, LLM extraction, vector search, or hypothesis ranking. The next pass should focus on search quality, evidence fidelity, traceability, and contract tests.

The current tool can produce a coherent local vault, but the generated review is still closer to a traceable evidence dump than a reliable literature review.

## Local Smoke Test Result

User ran:

```bash
knowcran discover "intracerebral hemorrhage" --limit 10
knowcran read-topic "intracerebral hemorrhage" --limit 10
knowcran export-obsidian "intracerebral hemorrhage"
knowcran review "intracerebral hemorrhage"
knowcran stats
```

Observed:

```text
Found 10 raw, 8 unique
Saved 8 papers to database
Extracted 20 claims from topic papers
Exported: 6 papers, 20 claims, 1 topic notes
Review generated with 20 evidence items and 6 papers
Papers: 8
Claims: 20
Links: 0
```

The pipeline runs end to end. That is good.

But the generated review has several quality problems:

- Search selected weak or tangential papers for the first page of results.
- Review bullets are hard-truncated mid-sentence.
- Bibliography has empty authors.
- Missing DOI is rendered as `doi = {None}`.
- Open questions do not cite source papers in the main review.
- Generic limitation placeholders dominate the limitations section.
- `Links: 0` is expected when `--expand` is not used, but the CLI should explain that to users.

## P0: Must Fix Before Adding Bigger Features

### 1. Fix Search Candidate Selection

Files:

```text
knowcran/semantic_scholar.py
knowcran/discovery.py
knowcran/utils.py
tests/test_discovery.py
tests/test_semantic_scholar_client.py
```

Problem:

`search_bulk()` calls `/graph/v1/paper/search/bulk` without a request-side limit, receives around 1000 records per generated query, then `discover()` keeps only `per_query = limit // len(queries)` from the front of each raw response.

For `limit=10`, this means only the first 2 records from each 1000-item response are considered before ranking.

In the local raw cache, some first-page examples were:

- `Developing Topics.`
- `Acute myeloid leukaemia induced by mitoxantrone: case report.`
- `Direct medical cost of stroke in Singapore`
- `Intracerebral hemorrhage and oral amphetamine.` from 1983

Meanwhile a more relevant result like `Hematoma Expansion following Intracerebral Hemorrhage: Mechanisms Targeting the Coagulation Cascade and Platelet Activation` appeared third in one response and was excluded from the `limit=10` run.

Required fix:

- Do not trim each generated query to `per_query` before global reranking.
- Fetch a reasonable candidate pool per query, then deduplicate and rank globally.
- For MVP, prefer the normal Semantic Scholar search endpoint for small interactive searches if it supports proper `limit` behavior better than bulk search.
- Add a `candidate_pool_per_query` internal setting, for example `max(20, ceil(limit * 2 / num_queries))`.
- Add phrase and field filters so obviously unrelated records do not survive just because of citation count or broad terms.

Acceptance tests:

- A mocked response where the best candidate is item 3 or item 10 must still be retained after discovery.
- A tangential high-citation paper should rank below a lower-citation paper with stronger title and abstract phrase match.
- `discover("intracerebral hemorrhage", limit=10)` should store up to 10 globally ranked papers, not 2 arbitrary front records from each generated query.

### 2. Add Real Semantic Scholar Client Contract Tests

Files:

```text
knowcran/semantic_scholar.py
tests/test_semantic_scholar_client.py
```

Problem:

`tests/test_semantic_scholar_client.py` is still missing in the repository. The client can drift from the real Semantic Scholar request contract while tests remain green.

Required tests using `httpx.MockTransport`:

- `search_bulk()` sends `GET /graph/v1/paper/search/bulk` with expected query params.
- `search_bulk()` follows `token` pagination and respects final caller limit.
- `get_paper()` sends `GET /graph/v1/paper/{paper_id}`.
- `batch_papers()` sends `POST /graph/v1/paper/batch` with JSON body `{"ids": [...]}`.
- `get_recommendations()` sends `POST /recommendations/v1/papers` with `positivePaperIds` and `negativePaperIds`.
- `get_recommendations_for_paper()` sends `GET /recommendations/v1/papers/forpaper/{paper_id}`.
- Cache hit returns cached JSON without network.
- Retries happen for `429`, `500`, `502`, `503`, and `504`.

Also test that cached JSON is written and read with explicit `encoding="utf-8"`.

### 3. Stop Truncating Evidence Mid-Sentence

Files:

```text
knowcran/review.py
knowcran/obsidian.py
tests/test_review.py
```

Problem:

Review and evidence matrix generation use hard slices like `claim_text[:200]` and topic notes use `claim_text[:150]`.

The local review contains broken text such as:

```text
Atypical intracerebral hemorrhage is th
used in guiding acute treatment a
hypoxic-ischemic en
```

This makes exported evidence look unreliable even when the stored abstract is fine.

Required fix:

- Store full claim text in the evidence matrix.
- For review Markdown, use sentence-aware or word-aware shortening only when necessary.
- If shortening is used, append an ellipsis and keep the original full claim available in the matrix.
- Do not cut Unicode text by raw character count if the result can split scientific notation or punctuation.

Acceptance tests:

- Evidence matrix contains full claim text.
- Review bullets never end with an obviously incomplete word fragment.
- Claims with Unicode punctuation and symbols remain readable.

### 4. Make Claim Extraction Idempotent

Files:

```text
knowcran/reading.py
knowcran/storage.py
tests/test_reading.py
```

Problem:

Every call to `read-topic` generates new UUIDs. Re-running the same command inserts duplicate claims because `claim_id` changes each time.

This will quickly pollute reviews after normal iterative use.

Required fix:

- Generate deterministic claim IDs from:
  - `paper_id`
  - `topic`
  - `evidence_type`
  - normalized claim text
  - `source_location`
- Or add a unique key such as `(paper_id, topic, evidence_type, source_location, claim_hash)`.
- Use upsert semantics for deterministic claim records.

Acceptance tests:

- Run `read_topic("celiac disease")` twice.
- Claim count must remain stable.
- Review evidence matrix must not duplicate identical evidence items.

### 5. Fix BibTeX Metadata

Files:

```text
knowcran/review.py
knowcran/bibtex.py
tests/test_review.py
```

Problems:

- `review.py` calls `json.loads()` inside `_build_bibtex()` but does not import `json`. The exception is swallowed, so all authors become empty.
- Missing DOI is exported as `doi = {None}`.
- BibTeX generation is embedded in `review.py` even though the project has a `bibtex.py` module in the planned structure.

Local bibliography showed:

```bibtex
author = {}
doi = {None}
```

Required fix:

- Move or centralize BibTeX generation in `knowcran/bibtex.py`.
- Import `json` explicitly if JSON strings are parsed.
- Omit optional fields when missing instead of writing `None`.
- Escape BibTeX-sensitive characters in title, author, journal, and DOI fields.
- Add tests with:
  - authors present
  - missing DOI
  - punctuation in title
  - hyphenated author names

### 6. Preserve Source Citations For Open Questions

Files:

```text
knowcran/review.py
knowcran/obsidian.py
```

Problem:

Main review open questions are listed without citations. The separate open questions file uses raw paper IDs instead of paper titles or citation keys.

Required fix:

- In review Markdown, render open questions with citations:

```markdown
- What population or cohort was studied? [@kalisvaart2020an]
```

- In the open questions file, include citation key, title, year, and paper note link if available.

Acceptance tests:

- Every open question in review text has a citation key.
- Every open question can be traced to a DB paper and a paper note.

## P1: Important Quality Improvements

### 7. Improve Relevance Scoring For Biomedical Search

Files:

```text
knowcran/utils.py
knowcran/discovery.py
tests/test_discovery.py
```

Current scoring is too simple:

- Query overlap uses substring matching.
- It does not strongly reward exact phrase matches.
- It does not penalize papers outside the disease context.
- It does not use `fieldsOfStudy`, `s2FieldsOfStudy`, venue, or abstract availability.

Recommended scoring changes:

- Tokenize query and text consistently.
- Add exact phrase boost for the original query.
- Add title phrase boost.
- Require at least one strong title or abstract match for narrow disease queries.
- Penalize no abstract for `read-topic` workflows.
- Prefer biomedical fields of study.
- Add configurable recency/citation weighting instead of hard-coded weights.

For ICH, the top 10 should prioritize review/mechanism/treatment/clinical papers about intracerebral hemorrhage, not broad stroke cost papers or unrelated leukemia case reports.

### 8. Clean Structured Abstract Headings Before Claim Extraction

Files:

```text
knowcran/reading.py
tests/test_reading.py
```

Problem:

The generated claims include raw abstract section labels:

```text
BACKGROUND
CONCLUSION
```

Required fix:

- Normalize common structured abstract labels:
  - `BACKGROUND`
  - `OBJECTIVE`
  - `METHODS`
  - `RESULTS`
  - `CONCLUSION`
- Keep the semantic role if useful, but do not dump the heading into the claim sentence.

### 9. Make Population/Open Question Detection Biomedical-Aware

Files:

```text
knowcran/reading.py
tests/test_reading.py
```

Problem:

The extractor asks `What population or cohort was studied?` for animal/model papers even when the abstract clearly says rat, mice, collagenase-induced ICH, or MCAO model.

Required fix:

- Detect animal/model terms:
  - `rat`
  - `mouse`
  - `mice`
  - `murine`
  - `collagenase-induced`
  - `middle cerebral artery occlusion`
  - `MCAO`
- Use a more specific open question:

```text
How well does this animal/model finding translate to human ICH?
```

### 10. Separate Placeholder Limitations From Extracted Limitations

Files:

```text
knowcran/reading.py
knowcran/review.py
tests/test_review.py
```

Problem:

`Needs full text review for limitations` is useful as a workflow marker, but it should not dominate the limitations section as if it were evidence.

Required fix:

- Either store placeholder limitations with a distinct evidence type, for example `full_text_needed`.
- Or keep `limitation` but add `is_placeholder`.
- Review output should separate:
  - extracted limitations
  - full-text follow-up needs

### 11. Track Topic Membership Explicitly

Files:

```text
knowcran/storage.py
knowcran/discovery.py
knowcran/reading.py
knowcran/review.py
```

Problem:

`get_papers_by_topic()` uses:

```sql
WHERE title LIKE ? OR abstract LIKE ?
```

This is not a reliable topic membership model. It can drop relevant expanded/recommended papers and include tangential papers that merely mention the phrase.

Recommended fix:

Add a table:

```sql
topic_papers(
  topic TEXT,
  paper_id TEXT,
  source TEXT,
  relevance_score REAL,
  created_at TEXT,
  PRIMARY KEY(topic, paper_id)
)
```

Then:

- `discover()` writes topic membership for selected papers.
- `read-topic()` reads from `topic_papers`.
- `review()` scopes papers through `topic_papers`.
- Text search remains a fallback, not the source of truth.

### 12. Clarify `Links: 0` In CLI Output

Files:

```text
knowcran/cli.py
README.md
```

`Links: 0` is expected when discovery is run without `--expand`, but users will read it as a failure.

Recommended change:

- In `stats`, print an explanatory hint when links are zero:

```text
Links: 0  (run discover --expand to collect references, citations, and recommendations)
```

## P2: Test Suite Hardening

### 13. Strengthen Citation-Key Tests

Files:

```text
tests/test_review.py
tests/test_mvp_flow.py
```

Problem:

The current MVP test extracts citation keys with:

```python
r"\[@(\w+)\]"
```

This misses valid keys containing hyphens, such as `el-sherif2023resource`.

Required fix:

- Use a regex that includes hyphen and colon, for example:

```python
r"\[@([A-Za-z0-9_:-]+)\]"
```

- Or parse citations more deliberately.
- Add a test with a hyphenated author name.

### 14. Add Realistic Biomedical Fixtures

Files:

```text
tests/fixtures/
tests/test_discovery.py
tests/test_reading.py
tests/test_review.py
```

Use small fixture sets for:

- Intracerebral hemorrhage
- Celiac disease
- A tangential high-citation distractor paper
- A structured abstract
- An animal model abstract
- A paper with missing DOI
- A paper with Unicode punctuation

This will catch most of the issues seen in the local ICH run.

### 15. Add Encoding Tests

Files:

```text
tests/test_obsidian.py
tests/test_review.py
tests/test_semantic_scholar_client.py
```

The local files are valid UTF-8 when read with explicit UTF-8, but Windows PowerShell displayed mojibake when using default encoding. To avoid cross-platform surprises:

- Use `encoding="utf-8"` for every `read_text()` and `write_text()`.
- Add tests with:
  - en dash
  - smart quotes
  - thin spaces
  - `≤`, `≥`

## Suggested PR Breakdown

### PR 1: Search And Discovery Quality

Scope:

- Fix candidate pool selection.
- Add global reranking before final trimming.
- Strengthen relevance scoring.
- Add realistic discovery tests.

Acceptance:

- The best candidate can be beyond the first 2 raw API results.
- Tangential high-citation distractors are demoted.
- `discover --limit` remains total and is tested.

### PR 2: Client Contract Tests

Scope:

- Add `tests/test_semantic_scholar_client.py`.
- Cover request paths, params, bodies, cache, retry, and pagination.

Acceptance:

- No real network calls in tests.
- Client API contract is locked down with `httpx.MockTransport`.

### PR 3: Evidence Fidelity

Scope:

- Remove hard truncation from evidence matrix.
- Sentence-aware shortening in Markdown.
- Idempotent claim IDs/upserts.
- Clean structured abstract labels.
- Improve biomedical open-question logic.

Acceptance:

- Re-running `read-topic` does not duplicate claims.
- Review bullets do not end mid-word.
- Animal/model abstracts get relevant follow-up questions.

### PR 4: Bibliography And Traceability

Scope:

- Fix BibTeX authors and missing DOI handling.
- Centralize BibTeX generation.
- Cite open questions.
- Strengthen citation-key tests.

Acceptance:

- Bibliography includes authors when available.
- Missing fields are omitted, not rendered as `None`.
- Every citation key in review and open questions exists in bibliography.

### PR 5: Topic Membership And UX

Scope:

- Add `topic_papers`.
- Route `read-topic`, `export-obsidian`, and `review` through explicit topic membership.
- Clarify `Links: 0` when `--expand` was not used.

Acceptance:

- Topic reviews use the exact discovered paper set unless the user asks for a text-search fallback.
- Users understand when link graph collection has not been run.

## Final Gate Before Next Feature Layer

Before adding PDF ingestion, LLM extraction, vector search, or Robin-like ranking, require:

```bash
pip install -e ".[dev]"
pytest
knowcran init
knowcran discover "intracerebral hemorrhage" --limit 10
knowcran read-topic "intracerebral hemorrhage" --limit 10
knowcran export-obsidian "intracerebral hemorrhage"
knowcran review "intracerebral hemorrhage"
knowcran stats
```

Expected:

- Tests pass without real network calls.
- Top discovered papers are recognizably relevant to the topic.
- Re-running `read-topic` does not duplicate claims.
- Review text has no mid-sentence hard truncation.
- Evidence matrix preserves full source claims.
- BibTeX has authors when Semantic Scholar provides authors.
- Missing DOI fields are omitted.
- Open questions cite source papers.
- Obsidian links resolve.
- `Links: 0` is either explained or nonzero after `--expand`.

