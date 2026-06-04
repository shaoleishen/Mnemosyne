"""PDF download and fetch subsystem for KnowCran.

This module handles downloading PDFs from multiple sources including
open access repositories, Sci-Hub, and LibGen. It provides DOI
normalization, arXiv ID detection, multi-source racing, and PDF
validation.

Default strategy is 'fastest' which races all sources in parallel.
Sci-Hub and LibGen are enabled by default per project decision.
See docs/fulltext-migration-notes.md for compliance considerations.
"""

from knowcran.paper_fetch.downloader import DownloadResult, download_pdf
from knowcran.paper_fetch.identifiers import (
    normalize_doi,
    detect_arxiv_id,
    is_valid_doi,
)
from knowcran.paper_fetch.pdf_utils import validate_pdf, safe_filename

__all__ = [
    "DownloadResult",
    "download_pdf",
    "normalize_doi",
    "detect_arxiv_id",
    "is_valid_doi",
    "validate_pdf",
    "safe_filename",
]
