from __future__ import annotations

import logging
import uuid
import json
import hashlib
from pathlib import Path
from typing import Any

import httpx

from knowcran.parsers.base import BaseParser, ParsedDocument, ParsedPage, ParsedElement
from knowcran.pdf_parse import _SECTION_PATTERNS  # Reuse section patterns

logger = logging.getLogger(__name__)

class MinerUParser(BaseParser):
    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")

    def parse(self, pdf_path: Path, paper_id: str, asset_id: str) -> ParsedDocument:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="mineru",
                parser_version="1.0.0",
                status="error",
                error=f"File not found: {pdf_path}",
            )

        # Retrieve file size
        file_size = pdf_path.stat().st_size
        source_hash = hashlib.sha256(pdf_path.name.encode()).hexdigest()[:16]

        try:
            logger.info(f"Uploading {pdf_path.name} to MinerU API at {self.api_url}")
            with open(pdf_path, "rb") as f:
                files = {"file": (pdf_path.name, f, "application/pdf")}
                # Call /file_parse or /tasks. We try /file_parse as it is standard synchronous.
                # Increase timeout to 180s for large files
                response = httpx.post(
                    f"{self.api_url}/file_parse",
                    files=files,
                    timeout=180.0
                )

            if response.status_code != 200:
                return ParsedDocument(
                    paper_id=paper_id,
                    asset_id=asset_id,
                    parser_name="mineru",
                    parser_version="1.0.0",
                    status="error",
                    error=f"MinerU API returned status {response.status_code}: {response.text}",
                )

            resp_data = response.json()
            # Standard mineru-api format: {"code": 200, "data": {"markdown": "...", "content_list": [...]}}
            data = resp_data.get("data", {}) if "data" in resp_data else resp_data

            markdown_text = data.get("markdown", "")
            content_list = data.get("content_list", [])

            if not markdown_text and not content_list:
                return ParsedDocument(
                    paper_id=paper_id,
                    asset_id=asset_id,
                    parser_name="mineru",
                    parser_version="1.0.0",
                    status="error",
                    error="MinerU API returned empty result",
                )

            pages: list[ParsedPage] = []
            elements: list[ParsedElement] = []
            current_section = None
            element_index = 0
            page_numbers_seen = set()

            # Process content_list layout elements if available
            if content_list and isinstance(content_list, list):
                for el in content_list:
                    text = el.get("text", el.get("markdown", "")).strip()
                    if not text:
                        continue

                    # Determine page index (0-indexed)
                    page_idx = el.get("page_idx", el.get("page_num", 1) - 1)
                    if page_idx < 0:
                        page_idx = 0
                    page_number = page_idx + 1

                    if page_number not in page_numbers_seen:
                        page_numbers_seen.add(page_number)
                        pages.append(ParsedPage(
                            page_id=str(uuid.uuid4()),
                            paper_id=paper_id,
                            page_idx=page_idx,
                            page_number=page_number,
                        ))

                    # Section detection
                    detected_section = self._detect_section(text)
                    if detected_section:
                        current_section = detected_section

                    el_type = el.get("type", "paragraph")
                    # Normalize type labels (e.g. text -> paragraph)
                    if el_type == "text":
                        el_type = "paragraph"

                    # Wrap formulas/equations in $$ ... $$ for proper rendering in Obsidian
                    if el_type in ("formula", "equation"):
                        if not (text.startswith("$$") or text.startswith("$")):
                            text = f"$$\n{text}\n$$"

                    elements.append(ParsedElement(
                        element_id=str(uuid.uuid4()),
                        paper_id=paper_id,
                        page_idx=page_idx,
                        element_type=el_type,
                        text=text,
                        bbox=el.get("bbox"),
                        section=current_section,
                        element_index=element_index,
                    ))
                    element_index += 1

            # Fallback: Parse markdown directly into paragraph blocks if no content_list
            if not elements and markdown_text:
                blocks = [b.strip() for b in markdown_text.split("\n\n") if b.strip()]
                for block in blocks:
                    # Heuristics: headings start with #
                    el_type = "paragraph"
                    text = block
                    if block.startswith("#"):
                        el_type = "heading"
                        text = block.lstrip("# ").strip()

                    detected_section = self._detect_section(text)
                    if detected_section:
                        current_section = detected_section

                    elements.append(ParsedElement(
                        element_id=str(uuid.uuid4()),
                        paper_id=paper_id,
                        page_idx=0,
                        element_type=el_type,
                        text=text,
                        section=current_section,
                        element_index=element_index,
                    ))
                    element_index += 1

                pages.append(ParsedPage(
                    page_id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    page_idx=0,
                    page_number=1,
                ))

            # Deduplicate / sort elements by index
            elements.sort(key=lambda e: (e.page_idx, e.element_index))
            pages.sort(key=lambda p: p.page_idx)

            # Compute content hash
            all_text = "\n\n".join(e.text for e in elements)
            content_hash = hashlib.sha256(all_text.encode()).hexdigest()[:16]

            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="mineru",
                parser_version="1.0.0",
                status="parsed",
                pages=pages,
                elements=elements,
                source_hash=source_hash,
                content_hash=content_hash,
            )

        except Exception as e:
            logger.error(f"MinerU API error: {e}")
            return ParsedDocument(
                paper_id=paper_id,
                asset_id=asset_id,
                parser_name="mineru",
                parser_version="1.0.0",
                status="error",
                error=f"MinerU parsing failed: {e}",
            )

    def _detect_section(self, text: str) -> str | None:
        head = text[:200]
        for pattern, section_name in _SECTION_PATTERNS:
            if pattern.search(head):
                return section_name
        return None
