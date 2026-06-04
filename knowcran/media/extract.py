"""Extract figure and table screenshots from PDF documents.

This module handles:
- Detecting figure/table elements from parsed document elements
- Extracting screenshots/images from PDF pages
- Normalizing figure/table labels (Figure 1, Fig. 1, 图1, Table 1, 表1)
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowcran.parsers.base import ParsedDocument, ParsedElement

logger = logging.getLogger(__name__)

# Regex patterns for figure/table labels
_FIGURE_LABEL_PATTERNS = [
    # English: Figure 1, Figure 1a, Fig. 1, Fig 1
    re.compile(r"(?:Figure|Fig\.?)\s*(\d+[a-z]?)", re.IGNORECASE),
    # Chinese: 图1, 图1a, 图 1
    re.compile(r"图\s*(\d+[a-z]?)"),
]

_TABLE_LABEL_PATTERNS = [
    # English: Table 1, Table 1a
    re.compile(r"Table\s*(\d+[a-z]?)", re.IGNORECASE),
    # Chinese: 表1, 表 1
    re.compile(r"表\s*(\d+[a-z]?)"),
]


@dataclass
class MediaAsset:
    """Represents an extracted media asset (figure or table)."""
    media_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str = ""
    asset_id: str = ""
    media_type: str = "figure"  # "figure" or "table"
    figure_label: str | None = None
    caption_text: str | None = None
    image_path: str = ""
    page_number: int | None = None
    bbox: list[float] | None = None
    ocr_text: str | None = None
    markdown_table: str | None = None
    extraction_method: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "paper_id": self.paper_id,
            "asset_id": self.asset_id,
            "media_type": self.media_type,
            "figure_label": self.figure_label,
            "caption_text": self.caption_text,
            "image_path": self.image_path,
            "page_number": self.page_number,
            "bbox": str(self.bbox) if self.bbox else None,
            "ocr_text": self.ocr_text,
            "markdown_table": self.markdown_table,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
        }


def normalize_label(label: str) -> str | None:
    """Normalize a figure or table label to a canonical form.

    Examples:
        "Figure 1" -> "Figure 1"
        "Fig. 1" -> "Figure 1"
        "fig 1a" -> "Figure 1a"
        "图1" -> "Figure 1"
        "Table 1" -> "Table 1"
        "表1" -> "Table 1"

    Returns None if no valid label is found.
    """
    text = label.strip()

    # Check figure patterns
    for pattern in _FIGURE_LABEL_PATTERNS:
        m = pattern.search(text)
        if m:
            num = m.group(1)
            return f"Figure {num}"

    # Check table patterns
    for pattern in _TABLE_LABEL_PATTERNS:
        m = pattern.search(text)
        if m:
            num = m.group(1)
            return f"Table {num}"

    return None


def detect_media_type(text: str) -> str | None:
    """Detect if text contains a figure or table label.

    Returns "figure", "table", or None.
    """
    for pattern in _FIGURE_LABEL_PATTERNS:
        if pattern.search(text):
            return "figure"
    for pattern in _TABLE_LABEL_PATTERNS:
        if pattern.search(text):
            return "table"
    return None


def is_media_element(element: ParsedElement) -> bool:
    """Check if a parsed element represents a figure or table."""
    if element.element_type in ("figure", "table"):
        return True
    # Also check text content for labels
    return detect_media_type(element.text) is not None


def extract_media_assets_from_elements(
    doc: ParsedDocument,
    output_dir: Path,
    pdf_path: Path | None = None,
) -> list[MediaAsset]:
    """Extract media assets from parsed document elements.

    This function:
    1. Identifies figure/table elements in the parsed document
    2. For MinerU-parsed docs, uses image paths if available
    3. For PyMuPDF-parsed docs, extracts screenshots from the PDF
    4. Normalizes labels and extracts captions

    Args:
        doc: Parsed document from MinerU or PyMuPDF parser
        output_dir: Directory to save extracted images
        pdf_path: Path to original PDF (needed for PyMuPDF screenshot extraction)

    Returns:
        List of MediaAsset objects
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    assets: list[MediaAsset] = []

    # Find figure/table elements
    media_elements = [e for e in doc.elements if is_media_element(e)]

    # Group by page for efficient extraction
    elements_by_page: dict[int, list[ParsedElement]] = {}
    for el in media_elements:
        elements_by_page.setdefault(el.page_idx, []).append(el)

    for page_idx, page_elements in elements_by_page.items():
        for element in page_elements:
            media_type = detect_media_type(element.text) or element.element_type
            if media_type not in ("figure", "table"):
                continue

            # Normalize label
            label = normalize_label(element.text)

            # Generate output path
            label_slug = label.replace(" ", "_").lower() if label else f"unlabeled_{element.element_index}"
            ext = ".png"
            image_filename = f"{doc.paper_id}_{label_slug}_{page_idx}{ext}"
            image_path = output_dir / image_filename

            # Try to extract screenshot if PDF path is available
            extracted = False
            if pdf_path and pdf_path.exists():
                extracted = _extract_region_from_pdf(
                    pdf_path, page_idx, element.bbox, image_path
                )

            asset = MediaAsset(
                paper_id=doc.paper_id,
                asset_id=doc.asset_id,
                media_type=media_type,
                figure_label=label,
                caption_text=element.text if len(element.text) > 20 else None,
                image_path=str(image_path) if extracted else "",
                page_number=page_idx + 1,
                bbox=element.bbox,
                extraction_method="pymupdf_crop" if extracted else "text_only",
                confidence=0.9 if extracted else 0.5,
            )
            assets.append(asset)

    return assets


def _extract_region_from_pdf(
    pdf_path: Path,
    page_idx: int,
    bbox: list[float] | None,
    output_path: Path,
) -> bool:
    """Extract a region from a PDF page as an image.

    Args:
        pdf_path: Path to the PDF file
        page_idx: 0-indexed page number
        bbox: Bounding box [x0, y0, x1, y1] or None for full page
        output_path: Path to save the extracted image

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        try:
            if page_idx >= len(doc):
                return False

            page = doc[page_idx]

            if bbox and len(bbox) == 4:
                # Extract specific region
                rect = pymupdf.Rect(bbox)
            else:
                # Extract full page
                rect = page.rect

            # Render at 2x resolution for better quality
            mat = pymupdf.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=rect)
            pix.save(str(output_path))
            return True
        finally:
            doc.close()
    except Exception as e:
        logger.warning(f"Failed to extract region from PDF: {e}")
        return False


def extract_media_from_mineru_response(
    content_list: list[dict[str, Any]],
    paper_id: str,
    asset_id: str,
    output_dir: Path,
) -> list[MediaAsset]:
    """Extract media assets directly from MinerU API response content_list.

    MinerU may return image elements with paths. This function extracts those
    and creates MediaAsset objects.

    Args:
        content_list: MinerU content_list from API response
        paper_id: Paper ID
        asset_id: Asset ID
        output_dir: Directory for saving extracted images

    Returns:
        List of MediaAsset objects
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    assets: list[MediaAsset] = []

    for el in content_list:
        el_type = el.get("type", "")

        # Check if this is a figure or table element
        if el_type not in ("image", "figure", "table"):
            # Also check text for labels
            text = el.get("text", el.get("markdown", ""))
            if not detect_media_type(text):
                continue
            media_type = detect_media_type(text)
        else:
            media_type = "figure" if el_type in ("image", "figure") else "table"

        text = el.get("text", el.get("markdown", ""))
        page_idx = el.get("page_idx", el.get("page_num", 1) - 1)

        # Check for image path from MinerU
        image_path = el.get("img_path", el.get("image_path", ""))

        # Normalize label
        label = normalize_label(text) if text else None

        # Generate output path if we have an image
        final_image_path = ""
        if image_path and Path(image_path).exists():
            label_slug = label.replace(" ", "_").lower() if label else f"unlabeled_{len(assets)}"
            ext = Path(image_path).suffix or ".png"
            out_filename = f"{paper_id}_{label_slug}_{page_idx}{ext}"
            final_image_path = str(output_dir / out_filename)

            # Copy image to output directory
            try:
                import shutil
                shutil.copy2(image_path, final_image_path)
            except Exception as e:
                logger.warning(f"Failed to copy image {image_path}: {e}")
                final_image_path = ""

        asset = MediaAsset(
            paper_id=paper_id,
            asset_id=asset_id,
            media_type=media_type,
            figure_label=label,
            caption_text=text if text and len(text) > 20 else None,
            image_path=final_image_path,
            page_number=page_idx + 1,
            bbox=el.get("bbox"),
            extraction_method="mineru_api" if final_image_path else "text_only",
            confidence=0.95 if final_image_path else 0.5,
        )
        assets.append(asset)

    return assets
