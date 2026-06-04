# Mnemosyne / KnowCran Release Guide & 1.0 Release Checklist

This guide documents the procedures for packaging, validating, and publishing a production-ready release candidate of `knowcran` on PyPI and GitHub. Promote the PyPI development classifier to `Production/Stable` only after every release gate has passed.

---

## 1. PyPI Release Checklist

Before publishing to PyPI, verify your local build distributions. The canonical release path is now the GitHub Actions release workflow, which uses PyPI Trusted Publishing.

### Build the Package
From the repository root with the virtual environment activated:
```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info

# Build source distribution and binary wheel
python -m build
```

### Validate Distributions
Run `twine check` to verify metadata and description parsing completeness:
```bash
python -m twine check dist/*
```
Ensure you receive the `PASSED` status for both `.whl` and `.tar.gz`.

### Test Clean Installation
Create a temporary blank environment and test clean installation:
```bash
python -m venv test_env
# Windows
.\test_env\Scripts\pip install dist/knowcran-1.0.0-py3-none-any.whl
.\test_env\Scripts\knowcran doctor
# Unix
./test_env/bin/pip install dist/knowcran-1.0.0-py3-none-any.whl
./test_env/bin/knowcran doctor
```

### Configure PyPI Trusted Publishing

In the PyPI project settings, add a trusted publisher for:

- repository: `shaoleishen/Mnemosyne`
- workflow: `release.yml`
- environment: `pypi`

Manual `twine upload` remains useful for TestPyPI dry runs, but production publishing should happen from the tag-triggered workflow.

---

## 2. GitHub Release Checklist

Prepare the GitHub Release with the built assets, checksums, and version notes. Pushing a `v*` tag triggers `.github/workflows/release.yml`, which builds the source distribution and wheel, publishes to PyPI, attaches artifacts and `SHA256SUMS.txt`, and creates the GitHub Release.

### Tag the Release
Tag the git commit and push the tag:
```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### Generate Checksums
The release workflow generates `dist/SHA256SUMS.txt`. For a local dry run, generate SHA256 checksums before uploading release assets:
```bash
cd dist
sha256sum * > SHA256SUMS.txt
```

### Release Body Template
Copy and populate this format for the GitHub Release description:

```markdown
# Release v1.0.0 (Production Baseline)

Mnemosyne `knowcran` version 1.0.0 is the first production-baseline release candidate of the local scientific discovery knowledge base.

## Key Deliverables
- **Out-of-the-box PDF layout parsing**: Powered by PyMuPDF and optional MinerU API.
- **Managed local production services**: Optional managed MinerU and OpenAI-compatible local embedding server.
- **GPU-aware execution**: `knowcran services start --gpu` and `knowcran run-topic --gpu` enable CUDA-oriented service settings for local workstations.
- **Concurrently downloading & parsing**: Parallelized downloading and layout parsing with configurable worker limits.
- **RRF Hybrid Search**: Merging SQLite FTS5 (BM25) and dense embeddings via Reciprocal Rank Fusion, with section boosts (Results, Methods).
- **E2E verification & doctor command**: Run `knowcran doctor` to inspect local system health.
- **Obsidian callout customizations**: Key claims formatted in structured callouts (`> [!success]`, `> [!warning]`) and LaTeX displays.

## Installation
```bash
pip install knowcran
# Or for managed local services and RAG
pip install "knowcran[local,rag]"
# Add GPU dependencies in a CUDA-prepared environment
pip install "knowcran[gpu]"
```

## Known Limitations
- Vector search similarity operates on CPU via in-memory list scans. Best suited for vaults with `< 10,000` chunks.
- MinerU managed Docker mode requires a locally built `mineru:latest` image. If `MNEMOSYNE_PDF_PARSER=auto` and MinerU is offline, the parser falls back automatically to PyMuPDF.
- Local embedding mode requires the `local` optional dependencies and a cached or downloadable embedding model.

## Checksums
| File | SHA256 Checksum |
| --- | --- |
| `knowcran-1.0.0-py3-none-any.whl` | `<insert whl SHA256>` |
| `knowcran-1.0.0.tar.gz` | `<insert tar.gz SHA256>` |

**PyPI URL**: [https://pypi.org/project/knowcran/](https://pypi.org/project/knowcran/)
```
