"""PDF parsing with PyMuPDF - extracts page-aware text chunks.

Parses PDFs into page-aware text chunks with section detection.
Handles empty/scanned PDFs and encrypted documents gracefully.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Section header patterns (case insensitive)
_SECTION_PATTERNS = [
    (re.compile(r"^\s*(?:abstract)\s*$", re.IGNORECASE | re.MULTILINE), "Abstract"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?introduction\s*$", re.IGNORECASE | re.MULTILINE), "Introduction"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:methods?|materials?\s*(?:and|&)\s*methods?|methodology|experimental(?:\s+(?:setup|procedures?))?)\s*$", re.IGNORECASE | re.MULTILINE), "Methods"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?results?\s*$", re.IGNORECASE | re.MULTILINE), "Results"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:discussion)\s*$", re.IGNORECASE | re.MULTILINE), "Discussion"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:conclusions?|summary)\s*$", re.IGNORECASE | re.MULTILINE), "Conclusion"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:references?|bibliography|literature\s+cited)\s*$", re.IGNORECASE | re.MULTILINE), "References"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:acknowledg?ments?)\s*$", re.IGNORECASE | re.MULTILINE), "Acknowledgments"),
    (re.compile(r"^\s*(?:\d+\.?\s*)?(?:supplementary|supporting\s+information)\s*$", re.IGNORECASE | re.MULTILINE), "Supplementary"),
]

# Target chunk size in words
TARGET_CHUNK_MIN = 800
TARGET_CHUNK_MAX = 1500


@dataclass
class PageText:
    """Text extracted from a single PDF page."""
    page_number: int  # 1-indexed
    text: str
    char_count: int = 0


@dataclass
class TextChunk:
    """A chunk of text spanning one or more pages."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str = ""
    asset_id: str = ""
    page_start: int = 0
    page_end: int = 0
    section: str | None = None
    chunk_index: int = 0
    text: str = ""
    text_hash: str = ""
    token_count: int = 0

    def __post_init__(self):
        if not self.text_hash and self.text:
            self.text_hash = hashlib.sha256(self.text.encode()).hexdigest()[:16]
        if not self.token_count and self.text:
            self.token_count = len(self.text.split())

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "asset_id": self.asset_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section": self.section,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "text_hash": self.text_hash,
            "token_count": self.token_count,
        }


@dataclass
class ParseResult:
    """Result of parsing a PDF."""
    success: bool
    paper_id: str
    asset_id: str
    total_pages: int = 0
    chunks: list[TextChunk] = field(default_factory=list)
    status: str = "parsed"  # parsed, needs_ocr, encrypted, error
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "paper_id": self.paper_id,
            "asset_id": self.asset_id,
            "total_pages": self.total_pages,
            "chunk_count": len(self.chunks),
            "status": self.status,
            "error": self.error,
        }


def parse_pdf(pdf_path: str | Path, paper_id: str = "", asset_id: str = "") -> ParseResult:
    """Parse a PDF file into page-aware text chunks.

    Uses PyMuPDF for text extraction. Detects empty/scanned PDFs
    and encrypted documents.
    """
    try:
        import pymupdf
    except ImportError:
        return ParseResult(
            success=False,
            paper_id=paper_id,
            asset_id=asset_id,
            status="error",
            error="pymupdf not installed",
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return ParseResult(
            success=False,
            paper_id=paper_id,
            asset_id=asset_id,
            status="error",
            error=f"File not found: {pdf_path}",
        )

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        error_str = str(e).lower()
        if "encrypted" in error_str or "password" in error_str:
            return ParseResult(
                success=False,
                paper_id=paper_id,
                asset_id=asset_id,
                status="encrypted",
                error="PDF is encrypted/password-protected",
            )
        return ParseResult(
            success=False,
            paper_id=paper_id,
            asset_id=asset_id,
            status="error",
            error=f"Failed to open PDF: {e}",
        )

    try:
        return _extract_text(doc, paper_id, asset_id)
    finally:
        doc.close()


def _extract_text(doc: Any, paper_id: str, asset_id: str) -> ParseResult:
    """Extract text from an opened PyMuPDF document."""
    pages: list[PageText] = []
    empty_pages = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if not text or not text.strip():
            empty_pages += 1
        pages.append(PageText(
            page_number=page_num + 1,
            text=text or "",
            char_count=len(text or ""),
        ))

    # Check if PDF appears to be scanned (mostly empty pages)
    if len(pages) > 0 and empty_pages / len(pages) > 0.8:
        return ParseResult(
            success=False,
            paper_id=paper_id,
            asset_id=asset_id,
            total_pages=len(pages),
            status="needs_ocr",
            error=f"{empty_pages}/{len(pages)} pages have no text (likely scanned)",
        )

    # Combine pages and chunk
    all_text = "\n\n".join(p.text for p in pages if p.text.strip())
    if not all_text.strip():
        return ParseResult(
            success=False,
            paper_id=paper_id,
            asset_id=asset_id,
            total_pages=len(pages),
            status="needs_ocr",
            error="No text extracted from PDF",
        )

    chunks = _chunk_text(pages, paper_id, asset_id)
    return ParseResult(
        success=True,
        paper_id=paper_id,
        asset_id=asset_id,
        total_pages=len(pages),
        chunks=chunks,
        status="parsed",
    )


def _chunk_text(pages: list[PageText], paper_id: str, asset_id: str) -> list[TextChunk]:
    """Split page text into chunks respecting page boundaries and section headers."""
    chunks: list[TextChunk] = []
    current_text = ""
    current_page_start = 1
    current_page_end = 1
    current_section: str | None = None
    chunk_index = 0

    for page in pages:
        if not page.text.strip():
            continue

        page_text = page.text
        # Detect section headers in this page
        detected_section = _detect_section(page_text)
        if detected_section:
            current_section = detected_section

        # If adding this page would exceed max chunk size, flush current chunk
        combined = current_text + "\n\n" + page_text if current_text else page_text
        word_count = len(combined.split())

        if word_count > TARGET_CHUNK_MAX and current_text.strip():
            # Flush current chunk
            chunk = TextChunk(
                paper_id=paper_id,
                asset_id=asset_id,
                page_start=current_page_start,
                page_end=current_page_end,
                section=current_section,
                chunk_index=chunk_index,
                text=current_text.strip(),
            )
            chunks.append(chunk)
            chunk_index += 1
            current_text = page_text
            current_page_start = page.page_number
            current_page_end = page.page_number
        else:
            current_text = combined
            current_page_end = page.page_number

    # Flush remaining text
    if current_text.strip():
        # If below minimum, try to merge with previous chunk
        word_count = len(current_text.split())
        if word_count < TARGET_CHUNK_MIN and chunks:
            prev = chunks[-1]
            prev.text = prev.text + "\n\n" + current_text.strip()
            prev.page_end = current_page_end
            prev.text_hash = hashlib.sha256(prev.text.encode()).hexdigest()[:16]
            prev.token_count = len(prev.text.split())
        else:
            chunk = TextChunk(
                paper_id=paper_id,
                asset_id=asset_id,
                page_start=current_page_start,
                page_end=current_page_end,
                section=current_section,
                chunk_index=chunk_index,
                text=current_text.strip(),
            )
            chunks.append(chunk)

    return chunks


def _detect_section(text: str) -> str | None:
    """Detect if text starts with a section header."""
    # Only check the first few lines
    head = text[:500]
    for pattern, section_name in _SECTION_PATTERNS:
        if pattern.search(head):
            return section_name
    return None
