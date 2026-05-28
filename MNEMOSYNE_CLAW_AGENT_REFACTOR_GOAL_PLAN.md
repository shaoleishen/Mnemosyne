# Mnemosyne Claw-Agent LLM Refactor Goal Plan

## Intent

Refactor Mnemosyne from a deterministic Semantic Scholar + regex evidence dumper into a traceable literature-research system whose LLM work is delegated through the local `claw-code-main` agent runtime. The goal is not to make the output more fluent first; the goal is to make discovery, extraction, review synthesis, and Obsidian export more trustworthy, idempotent, testable, and ready for long-running CC goal-mode execution.

This plan assumes:

- Mnemosyne remains a Python package and CLI.
- `claw-code-main` remains a sibling/local runtime, not vendored into Mnemosyne.
- Mnemosyne calls Claw through a subprocess adapter such as `claw prompt ...`.
- Claw is used as the LLM/agent execution source for structured extraction, relevance reranking, and review synthesis.
- Semantic Scholar remains the primary metadata source for this refactor.

## Scope

### In

- Add a clean LLM provider abstraction to Mnemosyne.
- Add a `ClawLLMProvider` that calls the local Claw binary.
- Use Claw for:
  - paper relevance reranking
  - abstract/full-text claim extraction when text is available
  - limitation/open-question extraction
  - evidence-aware review synthesis
- Keep all LLM outputs schema-validated before storage.
- Fix existing foundation problems discovered in the ICH smoke test:
  - weak search candidate selection
  - hard truncation
  - duplicate claims on repeated reads
  - broken/empty BibTeX metadata
  - topic membership via SQL `LIKE`
  - missing citations for open questions
  - weak client contract tests
- Remove or de-emphasize MVP-only functionality that conflicts with the new architecture.
- Add mocked tests so CI does not require real Claw, real LLM calls, or real Semantic Scholar network.
- Preserve a deterministic no-LLM fallback for low-resource/offline mode.

### Out

- Do not add Robin-like hypothesis ranking yet.
- Do not add vector search until extraction and topic membership are stable.
- Do not add multi-agent orchestration inside Mnemosyne itself.
- Do not make Claw mutate the Mnemosyne repository or runtime vault during normal LLM extraction calls.
- Do not require a specific provider key in tests.
- Do not make live network/API tests part of default CI.

## Target Architecture

```text
Mnemosyne CLI
  |
  |-- discovery.py
  |     |-- SemanticScholarClient
  |     |-- deterministic dedup/rank
  |     |-- optional LLM rerank through LLMProvider
  |
  |-- reading.py / extraction.py
  |     |-- deterministic fallback extractor
  |     |-- Claw-powered structured extractor
  |     |-- schema validation
  |
  |-- review.py
  |     |-- evidence matrix from DB only
  |     |-- Claw-powered narrative synthesis from claims only
  |
  |-- llm/
  |     |-- base.py
  |     |-- claw_provider.py
  |     |-- schemas.py
  |     |-- prompts.py
  |
  |-- storage.py
  |     |-- papers
  |     |-- topic_papers
  |     |-- claims
  |     |-- llm_runs
  |     |-- paper_links
  |
  |-- obsidian.py
  |-- bibtex.py
  |-- semantic_scholar.py
```

## Claw Integration Design

### Configuration

Add environment variables:

```text
MNEMOSYNE_LLM_PROVIDER=none|claw
MNEMOSYNE_CLAW_BIN=../claw-code-main/rust/target/debug/claw
MNEMOSYNE_CLAW_MODEL=sonnet
MNEMOSYNE_CLAW_PERMISSION_MODE=read-only
MNEMOSYNE_CLAW_TIMEOUT_SECONDS=600
MNEMOSYNE_CLAW_MAX_RETRIES=2
MNEMOSYNE_LLM_CACHE_DIR=data/raw/llm
```

On Windows, support:

```text
..\claw-code-main\rust\target\debug\claw.exe
```

Detection order:

1. `MNEMOSYNE_CLAW_BIN`
2. sibling `../claw-code-main/rust/target/debug/claw.exe`
3. sibling `../claw-code-main/rust/target/debug/claw`
4. `claw` on `PATH`

### Invocation Shape

Use subprocess, not direct Rust/Python coupling:

```bash
claw \
  --model "$MNEMOSYNE_CLAW_MODEL" \
  --permission-mode read-only \
  --output-format json \
  prompt "<schema-bound prompt>"
```

For local/OpenAI-compatible providers, Claw already supports:

```text
OPENAI_BASE_URL
OPENAI_API_KEY
DASHSCOPE_API_KEY
ANTHROPIC_API_KEY
ANTHROPIC_AUTH_TOKEN
```

Mnemosyne should not own provider routing. It should pass through the environment and let Claw route models.

### Security Boundary

For Mnemosyne's internal LLM calls:

- Default Claw permission mode must be `read-only`.
- Do not pass repository paths unless the task needs file context.
- Do not let Claw write Obsidian files or SQLite directly.
- Mnemosyne should own all persistence.
- Claw returns JSON; Mnemosyne validates and stores it.

For CC implementation goal mode:

- CC may run with broader permissions in the development repo.
- The runtime `ClawLLMProvider` inside Mnemosyne should still default to read-only.

## Data Model Changes

### Add `topic_papers`

Replace topic membership via `title LIKE ? OR abstract LIKE ?`.

```sql
CREATE TABLE IF NOT EXISTS topic_papers (
    topic TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    source TEXT NOT NULL,
    relevance_score REAL,
    llm_relevance_score REAL,
    llm_relevance_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(topic, paper_id),
    FOREIGN KEY(paper_id) REFERENCES papers(paper_id)
);
```

### Add `llm_runs`

Every Claw call should be auditable.

```sql
CREATE TABLE IF NOT EXISTS llm_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    task_type TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_json TEXT,
    raw_output TEXT,
    parsed_output_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);
```

### Upgrade `claims`

Add traceability and idempotency.

```sql
ALTER TABLE claims ADD COLUMN claim_hash TEXT;
ALTER TABLE claims ADD COLUMN source_text_hash TEXT;
ALTER TABLE claims ADD COLUMN source_span_json TEXT;
ALTER TABLE claims ADD COLUMN extraction_method TEXT;
ALTER TABLE claims ADD COLUMN is_placeholder INTEGER DEFAULT 0;
ALTER TABLE claims ADD COLUMN citation_key TEXT;
```

Add or emulate a uniqueness constraint:

```text
(paper_id, topic, evidence_type, source_location, claim_hash)
```

If SQLite migration complexity is high, create a new table and migrate data rather than layering fragile `ALTER TABLE` logic.

## LLM Schemas

Use Pydantic schemas and reject malformed LLM outputs.

### Relevance Rerank Output

```json
{
  "paper_id": "string",
  "is_relevant": true,
  "score": 0.0,
  "reason": "short reason",
  "topic_match": "direct|partial|tangential|irrelevant",
  "study_type": "review|clinical_trial|cohort|case_report|animal_model|mechanism|guideline|other"
}
```

### Claim Extraction Output

```json
{
  "paper_id": "string",
  "topic": "string",
  "study_type": "string",
  "population": "string|null",
  "model_or_system": "string|null",
  "methods": ["string"],
  "results": ["string"],
  "limitations": ["string"],
  "open_questions": ["string"],
  "full_text_needed": ["string"],
  "evidence_items": [
    {
      "evidence_type": "abstract_summary|method|result|limitation|open_question|full_text_needed",
      "claim_text": "string",
      "confidence": 0.0,
      "source_location": "abstract",
      "source_quote": "short exact quote from abstract",
      "source_span": {"start": 0, "end": 0}
    }
  ]
}
```

### Review Synthesis Output

```json
{
  "title": "string",
  "background": [{"text": "string", "citations": ["citation_key"]}],
  "main_evidence": [{"text": "string", "citations": ["citation_key"]}],
  "methods_and_models": [{"text": "string", "citations": ["citation_key"]}],
  "limitations": [{"text": "string", "citations": ["citation_key"]}],
  "open_questions": [{"text": "string", "citations": ["citation_key"]}],
  "warnings": ["string"]
}
```

Review synthesis must be constrained to stored evidence only. If the LLM references a citation key not in the selected paper set, reject the output and fall back to deterministic review generation.

## Features To Remove Or De-Emphasize

### Remove From Core Path

- Hard-coded regex-only claim extraction as the default when LLM is configured.
- Hard truncation in review and evidence matrix generation.
- Topic paper selection via `LIKE` as the primary behavior.
- Review synthesis that directly slices claim text and pretends to be a narrative.
- Any hidden swallowing of LLM/client errors.

### Keep As Fallback

- Deterministic abstract extraction under `MNEMOSYNE_LLM_PROVIDER=none`.
- Semantic Scholar raw cache.
- Basic Obsidian export.
- Deterministic review digest if LLM synthesis fails validation.

### Do Not Add Yet

- Vector index.
- PDF parsing beyond a placeholder interface.
- Multi-agent background orchestration from inside Mnemosyne.
- Hypothesis ranking.
- Autonomous database mutation by Claw.

## Long-Running CC Goal-Mode Prompt

Use this as the goal prompt for CC. It is intentionally broad and should be allowed to run for hours.

```text
Goal: Perform a large but controlled refactor of Mnemosyne so that Claw Code is the LLM execution source for relevance reranking, structured evidence extraction, and evidence-bound review synthesis.

Context:
- Mnemosyne is a Python CLI/package for Semantic Scholar discovery, SQLite storage, Obsidian export, and review generation.
- The sibling folder `claw-code-main` contains the Claw Code Rust agent runtime. Use it as an external subprocess provider, not as vendored Python code.
- Default runtime LLM calls from Mnemosyne must use Claw in read-only mode and return schema-validated JSON. Mnemosyne owns persistence.
- Existing deterministic behavior must remain available when `MNEMOSYNE_LLM_PROVIDER=none`.

Primary objectives:
1. Add an `LLMProvider` abstraction and a `ClawLLMProvider` subprocess adapter.
2. Add Pydantic schemas for relevance reranking, claim extraction, and review synthesis.
3. Add `topic_papers` and `llm_runs` storage, plus idempotent claim storage.
4. Fix discovery candidate selection so global reranking sees a real candidate pool before trimming.
5. Use optional LLM reranking after deterministic Semantic Scholar ranking.
6. Use optional LLM extraction for abstracts, with deterministic fallback.
7. Use optional LLM review synthesis from stored claims only, with citation-key validation.
8. Fix hard truncation, BibTeX metadata, missing DOI handling, and open-question citations.
9. Add mocked tests for Claw subprocess calls, schema validation, idempotency, discovery reranking, BibTeX, and review citation traceability.
10. Update README and CLI help so users understand Claw setup, provider env vars, no-LLM fallback, and validation behavior.

Constraints:
- Do not make live Claw, live LLM, or live Semantic Scholar calls in tests.
- Do not let Claw write Mnemosyne files during runtime extraction/review calls.
- Do not add vector search, PDF ingestion, or hypothesis ranking in this goal.
- Keep changes reviewable by module; avoid unrelated style churn.
- Preserve current CLI commands where possible, adding options rather than breaking them.

Implementation hints:
- Add `knowcran/llm/base.py`, `knowcran/llm/claw_provider.py`, `knowcran/llm/schemas.py`, and `knowcran/llm/prompts.py`.
- Add `knowcran/extraction.py` if `reading.py` is becoming too large.
- Move BibTeX generation into `knowcran/bibtex.py`.
- Add explicit UTF-8 encoding to file read/write paths.
- Use deterministic hashes for claim IDs or unique claim identity.
- Add a fake provider or fake subprocess runner for tests.

Validation:
- Run `pytest`.
- Run any available formatting/lint commands if configured.
- Run a local no-LLM smoke flow with mocked or cached data.
- If credentials and Claw binary are available, run one manual Claw smoke test but do not require it for tests.

Definition of done:
- `MNEMOSYNE_LLM_PROVIDER=none` still works.
- `MNEMOSYNE_LLM_PROVIDER=claw` uses Claw subprocess calls and validates JSON.
- Re-running `read-topic` does not duplicate claims.
- Review text has no mid-word truncation.
- Evidence matrix preserves full claims.
- Bibliography has authors when metadata provides them and omits missing DOI fields.
- Every review citation and open question citation maps to a selected DB paper.
- Topic reviews use `topic_papers`, not raw `LIKE`, as the primary source.
- Tests pass without network or real LLM calls.
```

## Action Items

### Phase 0: Repository And Runtime Orientation

[ ] Clone or open the Mnemosyne repository separately from `knowtest` runtime artifacts.

[ ] Inspect current files:

```text
knowcran/cli.py
knowcran/config.py
knowcran/discovery.py
knowcran/reading.py
knowcran/review.py
knowcran/obsidian.py
knowcran/bibtex.py
knowcran/storage.py
knowcran/semantic_scholar.py
knowcran/models.py
tests/
README.md
pyproject.toml
```

[ ] Inspect `claw-code-main` operational docs:

```text
claw-code-main/README.md
claw-code-main/USAGE.md
claw-code-main/docs/local-openai-compatible-providers.md
claw-code-main/docs/MODEL_COMPATIBILITY.md
```

[ ] Verify expected Claw binary path:

```powershell
E:\KNOWCRAN\claw-code-main\rust\target\debug\claw.exe
```

or:

```bash
../claw-code-main/rust/target/debug/claw
```

[ ] Run Claw health checks only if the local build and credentials are available:

```bash
claw doctor
claw --model sonnet --permission-mode read-only prompt "reply with READY"
```

Do not block implementation if credentials are absent; tests must use fakes.

### Phase 1: Configuration And Provider Abstraction

[ ] Add config fields for LLM provider selection:

```text
MNEMOSYNE_LLM_PROVIDER
MNEMOSYNE_CLAW_BIN
MNEMOSYNE_CLAW_MODEL
MNEMOSYNE_CLAW_PERMISSION_MODE
MNEMOSYNE_CLAW_TIMEOUT_SECONDS
MNEMOSYNE_CLAW_MAX_RETRIES
MNEMOSYNE_LLM_CACHE_DIR
```

[ ] Add `knowcran/llm/base.py` with:

```text
class LLMProvider(Protocol)
class LLMProviderError
class LLMValidationError
```

[ ] Add `knowcran/llm/claw_provider.py` with:

- binary detection
- subprocess invocation
- timeout handling
- retry handling
- raw output capture
- JSON extraction/parsing
- no direct DB writes

[ ] Add `knowcran/llm/fake_provider.py` or test fixture provider for unit tests.

[ ] Add tests:

```text
tests/test_llm_provider.py
tests/test_claw_provider.py
```

Test:

- binary path selection
- command construction
- timeout error
- nonzero exit handling
- malformed JSON rejection
- valid JSON parsing
- no live Claw call in tests

### Phase 2: LLM Schemas And Prompt Contracts

[ ] Add `knowcran/llm/schemas.py` with Pydantic models:

- `PaperRelevanceDecision`
- `PaperRerankOutput`
- `ExtractedEvidenceItem`
- `PaperExtractionOutput`
- `ReviewSectionItem`
- `ReviewSynthesisOutput`

[ ] Add `knowcran/llm/prompts.py` with prompt builders:

- `build_relevance_prompt(topic, papers)`
- `build_extraction_prompt(topic, paper)`
- `build_review_prompt(topic, papers, claims)`

[ ] Make every prompt demand strict JSON and explicitly forbid unsupported claims.

[ ] Add schema tests with:

- valid outputs
- missing fields
- extra citations
- invalid confidence values
- malformed source spans

### Phase 3: Storage Refactor

[ ] Add schema migrations or idempotent initialization for:

- `topic_papers`
- `llm_runs`
- upgraded `claims` fields

[ ] Add storage APIs:

```text
upsert_topic_paper(topic, paper_id, source, relevance_score, llm_relevance_score, reason)
get_topic_papers(topic, limit)
insert_llm_run(...)
upsert_claims_idempotent(...)
claim_hash(...)
```

[ ] Enable SQLite foreign keys where safe:

```sql
PRAGMA foreign_keys = ON;
```

[ ] Keep backwards compatibility for old local DBs if feasible.

[ ] Add tests:

```text
tests/test_topic_papers.py
tests/test_llm_runs_storage.py
tests/test_claim_idempotency.py
```

Required acceptance:

- `read-topic` twice does not increase claim count.
- `review(topic)` scopes through `topic_papers`.
- missing old migration columns do not crash init.

### Phase 4: Discovery Candidate Pool And Reranking

[ ] Fix `discover()` so it does not keep only `limit // len(queries)` arbitrary front results before ranking.

[ ] Introduce candidate-pool logic:

```text
candidate_pool_per_query = max(20, ceil(limit * 2 / query_count))
```

or a configurable equivalent.

[ ] Deduplicate globally before final trimming.

[ ] Improve deterministic relevance scoring:

- exact phrase boost
- title phrase boost
- abstract phrase boost
- biomedical field boost
- no-abstract penalty
- tangential/distractor penalty

[ ] Add optional LLM reranking:

```bash
knowcran discover "intracerebral hemorrhage" --limit 10 --llm-rerank
```

or make it automatic when:

```text
MNEMOSYNE_LLM_PROVIDER=claw
```

[ ] Store selected paper membership in `topic_papers`.

[ ] Add tests where the best paper appears beyond the first two API results.

[ ] Add tests with a high-citation tangential distractor.

### Phase 5: Reading And Evidence Extraction Refactor

[ ] Split deterministic extraction out of `reading.py` if it is too large:

```text
knowcran/extraction.py
```

[ ] Keep deterministic fallback extractor but stop making it the default when Claw is configured.

[ ] Implement Claw-powered extraction:

```text
extract_paper_claims_with_llm(topic, paper, provider)
```

[ ] Validate LLM output against `PaperExtractionOutput`.

[ ] Convert valid evidence items into idempotent `Claim` rows.

[ ] Store `extraction_method` as:

```text
deterministic
claw
```

[ ] Store placeholder limitations as `full_text_needed` or mark `is_placeholder=1`.

[ ] Improve biomedical open-question logic:

- distinguish human cohort from animal model
- distinguish review/guideline from original study
- generate translation questions for animal models
- avoid generic duplicate questions

[ ] Add tests:

- structured abstract headings are cleaned
- animal model produces translation open question
- repeated extraction is idempotent
- malformed LLM extraction falls back or fails visibly according to CLI option

### Phase 6: Review Generation Refactor

[ ] Make deterministic review generation a digest fallback, not the primary polished review when Claw is configured.

[ ] Build the review input exclusively from selected papers and stored claims.

[ ] Generate citation keys before calling Claw.

[ ] Claw review synthesis must return structured JSON, not free Markdown.

[ ] Validate that every citation key in review JSON exists in the selected paper set.

[ ] Render Markdown from validated structured review JSON.

[ ] Open questions must include citations.

[ ] Sections with no evidence must say:

```text
Needs evidence.
```

[ ] Do not hard-truncate evidence. If display shortening is needed, use sentence-aware shortening and preserve full text in CSV.

[ ] Add tests:

- invalid citation key rejects LLM review
- open question citations are preserved
- full claim text appears in evidence matrix
- review text has no mid-word truncation

### Phase 7: BibTeX And Obsidian Cleanup

[ ] Move BibTeX generation to `knowcran/bibtex.py`.

[ ] Fix missing `json` import behavior if authors are parsed from `authors_json`.

[ ] Omit missing DOI instead of writing:

```bibtex
doi = {None}
```

[ ] Escape BibTeX-sensitive characters.

[ ] Include authors when Semantic Scholar metadata contains them.

[ ] Add Obsidian paper and claim notes with:

- citation key
- topic membership
- extraction method
- source span/source quote when available

[ ] Use `encoding="utf-8"` for all Markdown/CSV/BibTeX reads and writes.

[ ] Add tests with:

- hyphenated author names
- missing DOI
- Unicode punctuation
- Obsidian link resolution

### Phase 8: CLI And README

[ ] Update CLI options:

```bash
knowcran discover TOPIC --limit 20 --llm-rerank / --no-llm-rerank
knowcran read-topic TOPIC --limit 20 --llm / --no-llm
knowcran review TOPIC --llm / --no-llm
knowcran llm-doctor
```

[ ] Add `knowcran llm-doctor` to check:

- selected provider
- Claw binary path
- Claw binary exists
- configured model
- permission mode
- raw one-shot prompt ability if user asks for live check

[ ] Keep live provider checks optional so normal diagnostics do not burn API credits unexpectedly.

[ ] Update README:

- Claw setup
- provider env vars
- local OpenAI-compatible provider path
- no-LLM fallback mode
- schema validation behavior
- limitations
- privacy and safety boundary

[ ] Update `.env.example`.

### Phase 9: Test And Validation Matrix

[ ] Run default tests:

```bash
pytest
```

[ ] Add no-network guarantee tests for:

- Semantic Scholar client through mocked transport
- Claw provider through fake subprocess
- review synthesis through fake provider

[ ] Run local smoke without LLM:

```bash
MNEMOSYNE_LLM_PROVIDER=none knowcran init
MNEMOSYNE_LLM_PROVIDER=none knowcran discover "intracerebral hemorrhage" --limit 10
MNEMOSYNE_LLM_PROVIDER=none knowcran read-topic "intracerebral hemorrhage" --limit 10
MNEMOSYNE_LLM_PROVIDER=none knowcran review "intracerebral hemorrhage"
```

[ ] If Claw is configured, run live smoke manually:

```bash
knowcran llm-doctor
MNEMOSYNE_LLM_PROVIDER=claw knowcran read-topic "intracerebral hemorrhage" --limit 3
MNEMOSYNE_LLM_PROVIDER=claw knowcran review "intracerebral hemorrhage" --max-papers 3
```

[ ] Compare outputs:

- no duplicate claims
- no hard truncation
- BibTeX authors present when available
- open questions cite source papers
- topic notes link to paper notes
- review citations map to bibliography

## Suggested Commit / PR Slices

### PR 1: LLM Provider Foundation

- Add config.
- Add LLM provider protocol.
- Add Claw subprocess provider.
- Add fake provider tests.
- Add `llm-doctor` skeleton.

### PR 2: Storage And Idempotency

- Add `topic_papers`.
- Add `llm_runs`.
- Add claim hashes.
- Add idempotent claim upsert.
- Route topic reads through `topic_papers`.

### PR 3: Discovery Quality

- Fix candidate pool.
- Improve deterministic relevance scoring.
- Add optional LLM reranking.
- Add discovery fixtures/tests.

### PR 4: Extraction

- Add LLM extraction schemas/prompts.
- Add Claw extraction path.
- Improve deterministic fallback.
- Add biomedical extraction tests.

### PR 5: Review And Bibliography

- Add LLM review synthesis.
- Validate citation keys.
- Fix BibTeX.
- Remove hard truncation.
- Add review traceability tests.

### PR 6: Docs And Smoke

- Update README and `.env.example`.
- Add operational docs for Claw.
- Add smoke test notes and examples.

## Risks And Mitigations

### Risk: Claw output is not clean JSON

Mitigation:

- Prompt for strict JSON.
- Extract first valid JSON object defensively.
- Validate with Pydantic.
- Store raw output in `llm_runs`.
- Fall back to deterministic mode or fail visibly based on CLI flag.

### Risk: LLM invents evidence

Mitigation:

- Review synthesis receives only stored claims.
- Every output item must carry citation keys.
- Reject unknown citation keys.
- Store source quotes and spans for extracted claims.

### Risk: Claw mutates files unexpectedly

Mitigation:

- Runtime provider uses `--permission-mode read-only`.
- Prompt does not include file-edit instructions.
- Mnemosyne owns all writes.

### Risk: Tests become slow or require credentials

Mitigation:

- Fake subprocess runner.
- Fake LLM provider.
- Mock Semantic Scholar transport.
- Live smoke tests are manual only.

### Risk: Refactor becomes too broad

Mitigation:

- Land in PR slices.
- Keep deterministic fallback working after every PR.
- Keep existing CLI commands compatible.
- Add tests before deleting MVP behavior.

## Definition Of Done

- `MNEMOSYNE_LLM_PROVIDER=none` works exactly as a local deterministic mode.
- `MNEMOSYNE_LLM_PROVIDER=claw` invokes Claw as the LLM source through a tested subprocess adapter.
- LLM outputs are schema-validated before storage or rendering.
- Topic membership is explicit through `topic_papers`.
- Re-running `read-topic` does not duplicate claims.
- Review text has no hard mid-word truncation.
- Evidence matrix preserves full claim text.
- BibTeX includes authors when available and omits missing optional fields.
- Open questions cite source papers.
- Every review citation maps to bibliography and selected DB papers.
- Obsidian claim links resolve to actual paper notes.
- Tests pass without network, Claw, or real LLM credentials.
- README explains Claw setup, provider routing, no-LLM mode, and limitations.

