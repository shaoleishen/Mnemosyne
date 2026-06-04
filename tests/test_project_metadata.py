"""Regression tests for release metadata and production readiness files."""

from __future__ import annotations

import tomllib
from pathlib import Path

import knowcran


ROOT = Path(__file__).resolve().parents[1]


def test_project_version_matches_package_version() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["version"] == "1.0.0"
    assert knowcran.__version__ == data["project"]["version"]


def test_required_release_documents_exist() -> None:
    required = [
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "ROADMAP.md",
        "SECURITY.md",
        "docs/fulltext-migration-notes.md",
        "docs/release/1.0.0-checklist.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        "scripts/verify-release.sh",
        "scripts/verify-release.ps1",
    ]

    missing = [path for path in required if not (ROOT / path).is_file()]

    assert missing == []


def test_readme_declares_1_0_0_status_and_limitations() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "1.0.0" in readme
    assert "Limitations" in readme
    assert "MCP Server Profiles" in readme
    assert "Evidence Contract" in readme


def test_ci_runs_cross_platform_matrix_and_package_build() -> None:
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")

    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "windows-latest" in workflow
    assert '"3.12"' in workflow
    assert '"3.13"' in workflow
    assert "python -m build" in workflow


def test_env_example_contains_no_real_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    forbidden_fragments = [
        "s2k-",
        "sk-",
        "ANTHROPIC_AUTH_TOKEN=tp-",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in env_example
