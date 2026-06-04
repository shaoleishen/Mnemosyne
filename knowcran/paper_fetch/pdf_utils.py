"""PDF validation, filename generation, and file utilities."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# PDF magic bytes
_PDF_MAGIC = b"%PDF"

# Maximum reasonable PDF size (100 MB)
MAX_PDF_SIZE = 100 * 1024 * 1024

# Minimum reasonable PDF size (1 KB)
MIN_PDF_SIZE = 1024

# Characters illegal in filenames on Windows
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_pdf(data: bytes) -> tuple[bool, str | None]:
    """Validate that bytes represent a valid PDF.

    Returns (is_valid, error_message).
    """
    if not data:
        return False, "Empty data"
    if len(data) < MIN_PDF_SIZE:
        return False, f"Too small ({len(data)} bytes)"
    if len(data) > MAX_PDF_SIZE:
        return False, f"Too large ({len(data)} bytes)"
    if not data[:4] == _PDF_MAGIC:
        return False, "Missing PDF magic bytes (%PDF)"
    # Check for %%EOF marker (may be followed by whitespace)
    if b"%%EOF" not in data[-1024:]:
        return False, "Missing %%EOF marker"
    return True, None


def safe_filename(
    title: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    fallback: str | None = None,
    max_len: int = 120,
) -> str:
    """Generate a safe filename for a PDF.

    Uses DOI if available, then arXiv ID, otherwise slugifies the title.
    """
    if doi:
        # Use DOI as base: 10.1234/example -> 10.1234_example
        name = doi.replace("/", "_").replace(":", "_")
    elif arxiv_id:
        name = arxiv_id.replace("/", "_").replace(":", "_")
    else:
        # Slugify title
        name = _ILLEGAL_CHARS.sub("_", (title or fallback or "paper").lower().strip())
        name = re.sub(r"_+", "_", name).strip("_")
        name = re.sub(r"\s+", "_", name)
        if not name:
            name = "paper"
    # Truncate
    if len(name) > max_len:
        name = name[:max_len].rstrip("_")
    return name + ".pdf"


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
