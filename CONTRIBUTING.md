# Contributing

Thanks for improving Mnemosyne / KnowCran. This project is a local-first scientific evidence tool, so changes should preserve traceability, reproducibility, and clear safety boundaries.

## Development Setup

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest -v
```

Python 3.12 or newer is required.

## Quality Gates

Before opening a pull request, run:

```bash
pytest -v
pytest --cov=knowcran --cov-report=term-missing
python -m compileall knowcran tests
python -m pip install build
python -m build
```

Or use the release verification helper:

```bash
bash scripts/verify-release.sh
```

On Windows PowerShell:

```powershell
.\scripts\verify-release.ps1
```

Network calls, live Semantic Scholar access, and live LLM calls must not be required by default tests. Use mocks, fixtures, or cached data for automated coverage.

## Evidence Rules

Any feature that generates or exposes knowledge must keep the evidence chain intact:

- `paper_id`
- `claim_id`
- `citation_key`
- `claim_text`
- `evidence_type`
- `confidence`
- `source_quote` or `evidence_status`

Do not present abstract-only evidence as full-text-reviewed evidence. Do not silently store unvalidated LLM output.

## MCP Safety

- Readonly profile must not write files, mutate SQLite data, or perform network discovery.
- Curate profile may discover, read, review, and export, but must respect configured data and vault directories.
- Admin profile is for local human maintenance only.

## Pull Request Checklist

- Tests cover the behavior change.
- Existing tests pass.
- Documentation is updated when CLI, MCP, data model, or release behavior changes.
- New network or LLM behavior has timeout, retry, and failure-path tests.
- New persistence behavior has migration or backward-compatibility tests.
