# Changelog

All notable changes to Mnemosyne / KnowCran are documented here.

## 1.0.0 - 2026-05-30

### Added

- Formal 1.0.0 project metadata and release documentation.
- Apache-2.0 license file.
- Production README with installation, MCP profile, evidence contract, testing, and limitation sections.
- Contributor guide, roadmap, and 1.0.0 release checklist.
- Cross-platform CI matrix for Linux, macOS, and Windows on Python 3.12 and 3.13.
- Static metadata regression tests for version consistency and required release artifacts.

### Changed

- Project version is now `1.0.0` in `pyproject.toml` and `knowcran.__version__`.
- Project status is now a production release candidate rather than alpha.
- CI now includes package build verification.

### Notes

- Full-text PDF ingestion, cloud multi-tenancy, and polished narrative review generation remain outside the 1.0.0 scope.
- Semantic Scholar remains the primary discovery source.
- LLM and agent providers remain optional; deterministic mode is still supported.
