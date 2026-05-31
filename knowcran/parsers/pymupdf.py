from __future__ import annotations

import logging
import uuid
import re
from pathlib import Path
from typing import Any

from knowcran.parsers.base import BaseParser, ParsedDocument, ParsedPage, ParsedElement
from knowcran.pdf_parse import _SECTION_PATTERNS  # Reuse section regexes

logger = logging.getLogger(__name__)

class PyMuPDFParser(BaseParser):
    def parse(self, pdf_path: Path, paper_id: str, asset_id: str) -> ParsedDocument:
        try:
            import pymupdf
        except ImportError:
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="error",
                error="pymupdf not installed",
            )

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="error",
                error=f"File not found: {pdf_path}",
            )

        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as e:
            error_str = str(e).lower()
            if "encrypted" in error_str or "password" in error_str:
                return ParsedDocument(
                    paper_id=paper_id,
                    asset_id=asset_id,
                    parser_name="pymupdf",
                    parser_version="1.0.0",
                    status="encrypted",
                    error="PDF is encrypted/password-protected",
                )
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="error",
                error=f"Failed to open PDF: {e}",
            )

        try:
            pages = []
            elements = []
            empty_pages = 0
            current_section = None
            element_index = 0

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                width = page.rect.width
                height = page.rect.height
                page_number = page_idx + 1

                parsed_page = ParsedPage(
                    page_id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    page_idx=page_idx,
                    page_number=page_number,
                    width=width,
                    height=height,
                )
                pages.append(parsed_page)

                blocks = page.get_text("blocks")
                if not blocks:
                    empty_pages += 1
                    continue

                for block in blocks:
                    x0, y0, x1, y1, text, block_no, block_type = block
                    text = text.strip()
                    if not text:
                        continue

                    # Section detection
                    detected_section = self._detect_section(text)
                    if detected_section:
                        current_section = detected_section

                    el_type = "paragraph"
                    if block_type == 1:
                        el_type = "figure"
                    elif self._is_heading(text):
                        el_type = "heading"

                    parsed_element = ParsedElement(
                        element_id=str(uuid.uuid4()),
                        paper_id=paper_id,
                        page_idx=page_idx,
                        element_type=el_type,
                        text=text,
                        bbox=[x0, y0, x1, y1],
                        section=current_section,
                        element_index=element_index,
                    )
                    elements.append(parsed_element)
                    element_index += 1

            if len(pages) > 0 and empty_pages / len(pages) > 0.8:
                return ParsedDocument(
                    paper_id=paper_id,
                    asset_id=asset_id,
                    parser_name="pymupdf",
                    parser_version="1.0.0",
                    status="needs_ocr",
                    error=f"{empty_pages}/{len(pages)} pages have no text (likely scanned)",
                    pages=pages,
                )

            if not elements:
                return ParsedDocument(
                    paper_id=paper_id,
                    asset_id=asset_id,
                    parser_name="pymupdf",
                    parser_version="1.0.0",
                    status="needs_ocr",
                    error="No text elements extracted from PDF",
                    pages=pages,
                )

            import hashlib
            # Generate hashes
            all_text = "\n\n".join(e.text for e in elements)
            source_hash = hashlib.sha256(pdf_path.name.encode()).hexdigest()[:16]
            content_hash = hashlib.sha256(all_text.encode()).hexdigest()[:16]

            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="parsed",
                pages=pages,
                elements=elements,
                source_hash=source_hash,
                content_hash=content_hash,
            )

        except Exception as e:
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="error",
                error=f"Parsing error: {e}",
            )
        finally:
            doc.close()

    def _detect_section(self, text: str) -> str | None:
        # Check first few lines of text block
        head = text[:200]
        for pattern, section_name in _SECTION_PATTERNS:
            if pattern.search(head):
                return section_name
        return None

    def _is_heading(self, text: str) -> bool:
        # Heading heuristics: short text, uppercase or title case, etc.
        lines = text.split("\n")
        if len(lines) > 2 or len(text) > 100:
            return False
        # Matches typical patterns like "1. Introduction" or "REFERENCES"
        if re.match(r"^\s*(?:\d+\.?\s*)?[A-Z][A-Za-z\s]{2,50}$", text):
            return True
        if text.isupper() and len(text) > 3:
            return True
        return False
