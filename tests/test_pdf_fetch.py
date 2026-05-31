"""Tests for the PDF fetch subsystem."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from knowcran.paper_fetch.identifiers import (
    normalize_doi,
    detect_arxiv_id,
    is_valid_doi,
    extract_doi_from_url,
)
from knowcran.paper_fetch.pdf_utils import (
    validate_pdf,
    safe_filename,
    compute_sha256,
)
from knowcran.paper_fetch.config import (
    Strategy,
    default_download_config,
    SourceConfig,
)
from knowcran.paper_fetch.downloader import DownloadResult


class TestNormalizeDoi:
    def test_valid_doi(self):
        assert normalize_doi("10.1234/example") == "10.1234/example"

    def test_doi_with_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1234/example") == "10.1234/example"

    def test_doi_with_dx_prefix(self):
        assert normalize_doi("http://dx.doi.org/10.1234/example") == "10.1234/example"

    def test_doi_uppercase(self):
        assert normalize_doi("10.1234/EXAMPLE") == "10.1234/example"

    def test_doi_with_trailing_slash(self):
        assert normalize_doi("10.1234/example/") == "10.1234/example"

    def test_doi_with_pdf_suffix(self):
        assert normalize_doi("10.1234/example.pdf") == "10.1234/example"

    def test_none_input(self):
        assert normalize_doi(None) is None

    def test_empty_string(self):
        assert normalize_doi("") is None

    def test_invalid_doi(self):
        assert normalize_doi("not-a-doi") is None


class TestIsValidDoi:
    def test_valid(self):
        assert is_valid_doi("10.1234/example") is True

    def test_invalid(self):
        assert is_valid_doi("not-a-doi") is False

    def test_with_whitespace(self):
        assert is_valid_doi("  10.1234/example  ") is True


class TestDetectArxivId:
    def test_bare_id(self):
        assert detect_arxiv_id("2301.12345") == "2301.12345"

    def test_versioned_id(self):
        assert detect_arxiv_id("2301.12345v2") == "2301.12345v2"

    def test_url_abs(self):
        assert detect_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"

    def test_url_pdf(self):
        assert detect_arxiv_id("https://arxiv.org/pdf/2301.12345") == "2301.12345"

    def test_none_input(self):
        assert detect_arxiv_id(None) is None

    def test_no_id(self):
        assert detect_arxiv_id("no id here") is None


class TestExtractDoiFromUrl:
    def test_doi_org_url(self):
        assert extract_doi_from_url("https://doi.org/10.1234/example") == "10.1234/example"

    def test_non_doi_url(self):
        assert extract_doi_from_url("https://example.com/paper") is None

    def test_none_input(self):
        assert extract_doi_from_url(None) is None


class TestValidatePdf:
    def test_valid_pdf(self):
        # Minimal valid PDF
        data = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 0\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
        # Pad to minimum size
        data = data + b"\x00" * (1024 - len(data) + 100)
        valid, err = validate_pdf(data)
        assert valid is True
        assert err is None

    def test_empty_data(self):
        valid, err = validate_pdf(b"")
        assert valid is False
        assert "Empty" in err

    def test_too_small(self):
        valid, err = validate_pdf(b"%PDF")
        assert valid is False
        assert "Too small" in err

    def test_wrong_magic(self):
        data = b"NOT PDF" + b"\x00" * 2000
        valid, err = validate_pdf(data)
        assert valid is False
        assert "Missing PDF magic" in err


class TestSafeFilename:
    def test_with_doi(self):
        name = safe_filename("Test Paper", doi="10.1234/example")
        assert name == "10.1234_example.pdf"

    def test_with_title(self):
        name = safe_filename("My Test Paper: A Study")
        assert name.endswith(".pdf")
        assert ":" not in name

    def test_long_title(self):
        name = safe_filename("A" * 200)
        assert len(name) <= 125  # 120 + .pdf


class TestComputeSha256:
    def test_deterministic(self):
        h1 = compute_sha256(b"test data")
        h2 = compute_sha256(b"test data")
        assert h1 == h2

    def test_different_data(self):
        h1 = compute_sha256(b"data1")
        h2 = compute_sha256(b"data2")
        assert h1 != h2


class TestStrategy:
    def test_fastest(self):
        config = default_download_config(strategy="fastest")
        assert config.strategy == Strategy.FASTEST
        sources = config.get_enabled_sources()
        # Should include both OA and grey sources
        names = [s.name for s in sources]
        assert "Sci-Hub" in names
        assert "LibGen" in names

    def test_legal_only(self):
        config = default_download_config(strategy="legal_only")
        sources = config.get_enabled_sources()
        names = [s.name for s in sources]
        assert "Sci-Hub" not in names
        assert "LibGen" not in names
        assert "arXiv" in names

    def test_scihub_only(self):
        config = default_download_config(strategy="scihub_only")
        sources = config.get_enabled_sources()
        names = [s.name for s in sources]
        assert names == ["Sci-Hub"]

    def test_disabled_scihub(self):
        config = default_download_config(strategy="fastest", scihub_enabled=False)
        sources = config.get_enabled_sources()
        names = [s.name for s in sources]
        assert "Sci-Hub" not in names


class TestDownloadResult:
    def test_to_dict(self):
        result = DownloadResult(
            success=True,
            identifier="10.1234/example",
            doi="10.1234/example",
            source="arXiv",
            file_path="/tmp/test.pdf",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["identifier"] == "10.1234/example"
        assert d["source"] == "arXiv"
