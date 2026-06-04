from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class ParsedElement:
    element_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str = ""
    page_idx: int = 0
    element_type: str = "paragraph"  # heading, paragraph, table, equation, figure, list_item
    text: str = ""
    bbox: list[float] | None = None  # [x0, y0, x1, y1]
    section: str | None = None
    element_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        import json
        return {
            "element_id": self.element_id,
            "paper_id": self.paper_id,
            "page_idx": self.page_idx,
            "element_type": self.element_type,
            "text": self.text,
            "bbox": json.dumps(self.bbox) if self.bbox else None,
            "section": self.section,
            "element_index": self.element_index,
        }

@dataclass
class ParsedPage:
    page_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str = ""
    page_idx: int = 0
    page_number: int = 1
    width: float | None = None
    height: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "paper_id": self.paper_id,
            "page_idx": self.page_idx,
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
        }

@dataclass
class ParsedDocument:
    paper_id: str
    asset_id: str
    parser_name: str
    parser_version: str
    status: str  # parsed, needs_ocr, encrypted, error
    error: str | None = None
    pages: list[ParsedPage] = field(default_factory=list)
    elements: list[ParsedElement] = field(default_factory=list)
    source_hash: str | None = None
    content_hash: str | None = None

class BaseParser:
    def parse(self, pdf_path: Path, paper_id: str, asset_id: str) -> ParsedDocument:
        """Parse a PDF file.
        
        Returns a ParsedDocument containing metadata, pages, and layout elements.
        """
        raise NotImplementedError
