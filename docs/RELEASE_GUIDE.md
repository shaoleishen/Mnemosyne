# Mnemosyne / KnowCran Release Guide & 1.0 Release Checklist

This guide documents the procedures for packaging, validating, and publishing a production-ready release of `knowcran` on PyPI and GitHub.

---

## 1. PyPI Release Checklist

Before uploading to PyPI, verify your local build distributions.

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

### Upload to PyPI
Use `twine` to securely upload the distribution files:
```bash
# Upload to TestPyPI first (optional but recommended)
python -m twine upload --repository testpypi dist/*

# Upload to PyPI Production
python -m twine upload dist/*
```

---

## 2. GitHub Release Checklist

Prepare the GitHub Release with the built assets, checksums, and version notes.

### Tag the Release
Tag the git commit and push the tag:
```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### Generate Checksums
Generate SHA256 checksums for the build assets:
- **Windows**:
  ```cmd
  certutil -hashfile dist/knowcran-1.0.0-py3-none-any.whl SHA256
  certutil -hashfile dist/knowcran-1.0.0.tar.gz SHA256
  ```
- **Unix**:
  ```bash
  sha256sum dist/knowcran-1.0.0-py3-none-any.whl
  sha256sum dist/knowcran-1.0.0.tar.gz
  ```

### Release Body Template
Copy and populate this format for the GitHub Release description:

```markdown
# Release v1.0.0 (Production Ready)

Mnemosyne `knowcran` version 1.0.0 is the first official production-ready release of the local scientific discovery knowledge base.

## Key Deliverables
- **Out-of-the-box PDF layout parsing**: Powered by PyMuPDF and optional MinerU API.
- **Concurrently downloading & parsing**: Parallelized downloading (5 threads) and layout parsing (3 threads).
- **RRF Hybrid Search**: Merging SQLite FTS5 (BM25) and dense embeddings via Reciprocal Rank Fusion, with section boosts (Results, Methods).
- **E2E verification & doctor command**: Run `knowcran doctor` to inspect local system health.
- **Obsidian callout customizations**: Key claims formatted in structured callouts (`> [!success]`, `> [!warning]`) and LaTeX displays.

## Installation
```bash
pip install knowcran
# Or for advanced PDF layout extraction and RAG
pip install "knowcran[pdf,rag]"
```

## Known Limitations
- Vector search similarity operates on CPU via in-memory list scans. Best suited for vaults with `< 10,000` chunks.
- MinerU layout parsing requires a running local `mineru-api` service. If offline, the parser falls back automatically to PyMuPDF.

## Checksums
| File | SHA256 Checksum |
| --- | --- |
| `knowcran-1.0.0-py3-none-any.whl` | `<insert whl SHA256>` |
| `knowcran-1.0.0.tar.gz` | `<insert tar.gz SHA256>` |

**PyPI URL**: [https://pypi.org/project/knowcran/](https://pypi.org/project/knowcran/)
```
