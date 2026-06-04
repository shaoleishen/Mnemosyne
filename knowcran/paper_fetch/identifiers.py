"""DOI, PMID, and arXiv identifier normalization and detection."""

from __future__ import annotations

import re

# DOI pattern: starts with 10. followed by registrant code / suffix
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s]+$")
_DOI_URL_PATTERN = re.compile(r"https?://(?:dx\.)?doi\.org/(.+)", re.IGNORECASE)
_ARXIV_ID_PATTERN = re.compile(
    r"(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)
_ARXIV_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)


def normalize_doi(raw: str | None) -> str | None:
    """Normalize a DOI to lowercase, strip URL prefix and whitespace.

    Returns None if input is None or doesn't look like a DOI.
    """
    if not raw:
        return None
    doi = raw.strip()
    # Strip URL prefix
    m = _DOI_URL_PATTERN.match(doi)
    if m:
        doi = m.group(1)
    # Strip trailing slash or .pdf
    doi = re.sub(r"[/\.](?:pdf|html|full)?/?$", "", doi, flags=re.IGNORECASE)
    doi = doi.strip().lower()
    if _DOI_PATTERN.match(doi):
        return doi
    return None


def is_valid_doi(doi: str) -> bool:
    """Check if a string looks like a valid DOI."""
    return _DOI_PATTERN.match(doi.strip()) is not None


def detect_arxiv_id(text: str | None) -> str | None:
    """Extract an arXiv ID from a string (URL, citation, or bare ID).

    Returns the normalized arXiv ID (e.g., '2301.12345') or None.
    """
    if not text:
        return None
    # Try URL pattern first
    m = _ARXIV_URL_PATTERN.search(text)
    if m:
        return m.group(1)
    # Try bare ID pattern
    m = _ARXIV_ID_PATTERN.search(text)
    if m:
        return m.group(1)
    return None


def extract_doi_from_url(url: str) -> str | None:
    """Extract a DOI from a URL that may contain one."""
    if not url:
        return None
    m = _DOI_URL_PATTERN.match(url)
    if m:
        return normalize_doi(m.group(1))
    return None
