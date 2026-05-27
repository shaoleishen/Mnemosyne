# Task: Implement Semantic Scholar Local Scientific Discovery Knowledge Base

Please implement a Python MVP project in the current workspace. The project should use the Semantic Scholar API instead of Edison to build a local life-science literature discovery, reading, Obsidian knowledge base, and literature review generation system.

## Goal

Implement a runnable CLI tool that supports:

1. Input a disease or research question and search papers through Semantic Scholar.
2. Deduplicate, rank, and save paper metadata to SQLite.
3. Fetch paper details, references, citations, and recommended papers.
4. Generate local paper notes, evidence entries, limitation entries, and open questions from abstracts.
5. Export an Obsidian Markdown knowledge base.
6. Generate literature reviews, evidence matrices, BibTeX files, and open question documents from stored evidence.
7. Avoid any dependency on Edison, Future House, or closed-source agents.

## Technical Stack

- Python 3.12+
- `httpx` for Semantic Scholar API calls
- `pydantic` for models
- `typer` for CLI
- `rich` for terminal output
- stdlib `sqlite3` for SQLite
- `pytest` for tests
- Optional: `python-dotenv`

## Project Structure

Create:

```text
knowcran/
  __init__.py
  cli.py
  config.py
  models.py
  semantic_scholar.py
  storage.py
  discovery.py
  reading.py
  obsidian.py
  review.py
  bibtex.py
  utils.py
tests/
  test_dedup.py
  test_cache.py
  test_storage.py
  test_obsidian.py
  test_review.py
pyproject.toml
README.md
.env.example
```

The runtime data directories should be created automatically:

```text
data/
  knowcran.sqlite
  raw/semantic_scholar/
vault/
  papers/
  claims/
  topics/
  reviews/
  templates/
```

## Configuration

Support these environment variables:

```text
SEMANTIC_SCHOLAR_API_KEY=
KNOWCRAN_DATA_DIR=data
KNOWCRAN_VAULT_DIR=vault
KNOWCRAN_RATE_LIMIT_SECONDS=1.1
```

The system must still allow low-frequency API calls without an API key.

## Semantic Scholar Client

Implement `SemanticScholarClient` with:

- `search_bulk(query, limit=100, fields=...)`
- `get_paper(paper_id, fields=...)`
- `batch_papers(paper_ids, fields=...)`
- `get_recommendations(seed_paper_ids, positive_paper_ids=None, negative_paper_ids=None, limit=20)`
- `get_recommendations_for_paper(paper_id, limit=20)`

Default fields:

```text
paperId,title,abstract,year,publicationDate,venue,authors,externalIds,
citationCount,referenceCount,influentialCitationCount,fieldsOfStudy,
s2FieldsOfStudy,openAccessPdf,url,references,citations
```

All requests must use:

- Rate limiting, default one request every 1.1 seconds.
- Retry handling for `429`, `500`, `502`, `503`, and `504`.
- Raw JSON cache saved under `data/raw/semantic_scholar/`.
- Cache keys based on `method + url + query/body` using SHA-256.

## SQLite Schema

Implement database initialization and upsert logic.

```sql
papers(
  paper_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  abstract TEXT,
  year INTEGER,
  publication_date TEXT,
  venue TEXT,
  url TEXT,
  doi TEXT,
  pmid TEXT,
  arxiv_id TEXT,
  citation_count INTEGER,
  reference_count INTEGER,
  influential_citation_count INTEGER,
  fields_json TEXT,
  authors_json TEXT,
  external_ids_json TEXT,
  open_access_pdf_json TEXT,
  discovered_by TEXT,
  relevance_score REAL,
  created_at TEXT,
  updated_at TEXT
)

paper_links(
  source_paper_id TEXT,
  target_paper_id TEXT,
  link_type TEXT,
  created_at TEXT,
  PRIMARY KEY(source_paper_id, target_paper_id, link_type)
)

claims(
  claim_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  evidence_type TEXT,
  confidence REAL,
  source_location TEXT,
  topic TEXT,
  created_at TEXT
)

runs(
  run_id TEXT PRIMARY KEY,
  command TEXT,
  query TEXT,
  params_json TEXT,
  created_at TEXT
)
```

`paper_links.link_type` values should include:

- `reference`
- `citation`
- `recommendation`

`claims.evidence_type` values should include:

- `abstract_summary`
- `method`
- `result`
- `limitation`
- `open_question`

## Data Models

Use Pydantic to define:

- `ResearchQuestion`
- `PaperRecord`
- `PaperLink`
- `Claim`
- `EvidenceMatrixRow`
- `ReviewRequest`
- `ReviewOutput`

`PaperRecord` must parse DOI, PMID, and ArXiv IDs from Semantic Scholar JSON.

## Discovery Workflow

Implement `discover(question: str, limit: int, expand: bool)`.

Steps:

1. Generate 3-5 queries:
   - Original question
   - `{question} mechanism`
   - `{question} treatment`
   - `{question} review`
   - `{question} clinical`
2. Call Semantic Scholar bulk search for each query.
3. Deduplicate using this priority:
   - `paperId`
   - DOI
   - PMID
   - normalized title
4. Calculate `relevance_score` using:
   - title/query overlap
   - abstract/query overlap
   - log citation count score
   - publication recency
   - open access bonus
5. Write papers to SQLite.
6. If `expand=True`:
   - Fetch references and citations for top papers.
   - Fetch recommendations.
   - Write links to `paper_links`.

Each paper should record its discovery source:

- `keyword_search`
- `citation_expansion`
- `reference_expansion`
- `recommendation`
- `manual_import`

## Reading Workflow

Implement:

- `read_paper(paper_id)`
- `read_topic(topic, limit=20)`

Version 1 should not require an LLM. Use deterministic abstract extraction:

- `abstract_summary`: the first 1-2 abstract sentences or the full short abstract.
- `method`: sentences containing terms such as `method`, `model`, `cohort`, `trial`, `assay`, or `dataset`.
- `result`: sentences containing terms such as `show`, `demonstrate`, `associated`, `increased`, `decreased`, or `significant`.
- `limitation`: if the abstract has no explicit limitation, create `needs full text review`.
- `open_question`: generate 1-3 questions based on missing method, population, mechanism, or intervention details.

Every claim must bind:

- `paper_id`
- `source_location="abstract"`
- `confidence`
- `evidence_type`

## Obsidian Export

Implement:

- Paper notes: `vault/papers/{year}_{slug_title}.md`
- Claim notes: `vault/claims/{claim_id}.md`
- Topic notes: `vault/topics/{slug_topic}.md`

Paper note frontmatter:

```yaml
---
paper_id:
title:
year:
venue:
doi:
pmid:
citation_count:
discovered_by:
status: unread|read|reviewed
tags:
  - paper
  - semantic-scholar
---
```

Paper note body:

```markdown
# Title

## Metadata

## Abstract

## Key Claims

## Methods

## Limitations

## Open Questions

## Links
```

## Review Generation

Implement `review(topic, max_papers=20)`.

The review generator may only use claims already stored in SQLite. It must not invent conclusions without evidence.

Output:

```text
vault/reviews/{slug_topic}_review.md
vault/reviews/{slug_topic}_evidence_matrix.csv
vault/reviews/{slug_topic}_bibliography.bib
vault/reviews/{slug_topic}_open_questions.md
```

Review structure:

```markdown
# Literature Review: {topic}

## Background

## Main Evidence

## Methods And Models

## Limitations

## Open Questions

## References
```

Requirements:

- Every evidence item should include a citation key.
- Sections without evidence should say `needs evidence`.
- Bibliography should be generated from stored paper metadata.

## CLI

Implement these commands:

```bash
knowcran init
knowcran discover "idiopathic pulmonary fibrosis" --limit 50 --expand
knowcran read-paper PAPER_ID
knowcran read-topic "idiopathic pulmonary fibrosis" --limit 20
knowcran export-obsidian --topic "idiopathic pulmonary fibrosis"
knowcran review "idiopathic pulmonary fibrosis" --max-papers 20
knowcran show-paper PAPER_ID
knowcran stats
```

Expose the CLI in `pyproject.toml`:

```toml
[project.scripts]
knowcran = "knowcran.cli:app"
```

## Tests

Implement and pass:

1. DOI, PMID, `paperId`, and normalized-title deduplication tests.
2. Stable Semantic Scholar cache key tests.
3. SQLite initialization, upsert, and query tests.
4. Obsidian Markdown frontmatter tests.
5. Review citation traceability tests: every review citation must correspond to a database paper.
6. No real network calls in tests; use mocked Semantic Scholar responses.

## README

Document:

- Project goal.
- Why Edison is not used.
- How to configure `SEMANTIC_SCHOLAR_API_KEY`.
- CLI examples.
- Data directory structure.
- Obsidian vault usage.
- Current limitations:
  - abstract-only reading
  - Semantic Scholar rate limits
  - no LLM extraction yet
- Next steps:
  - PDF full text ingestion
  - LLM claim extraction
  - vector index
  - Robin-like hypothesis ranking

## Acceptance Criteria

After implementation, these commands should work:

```bash
pip install -e ".[dev]"
knowcran init
knowcran discover "celiac disease" --limit 10
knowcran read-topic "celiac disease" --limit 5
knowcran review "celiac disease"
pytest
```

The system should still work in low-frequency mode without a Semantic Scholar API key.

## Version Management Notes

- Keep the first implementation small and reviewable.
- Commit the MVP as one initial GitHub push.
- Avoid adding Robin or Edison as dependencies.
- Keep generated runtime data (`data/`, `vault/`) out of source control unless sample fixtures are intentionally added.
- Prefer adding sample mocked fixtures under `tests/fixtures/`.
- After Claude Code completes implementation and pushes to GitHub, the next review pass should inspect:
  - API client reliability
  - data model boundaries
  - evidence traceability
  - test coverage
  - whether the system can evolve toward PDF, LLM extraction, and hypothesis ranking
```
