"""Convert table screenshots to Markdown using Vision API.

This module provides:
- Table screenshot to Markdown conversion
- OCR text extraction for tables
- Integration with Vision API providers
"""

from __future__ import annotations

import logging
import hashlib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def table_to_markdown(
    image_path: str | Path,
    provider: Any | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Convert a table screenshot to Markdown format.

    Args:
        image_path: Path to the table screenshot image
        provider: Vision API provider instance (optional)
        prompt: Custom prompt for the Vision API (optional)

    Returns:
        Dict with:
            - markdown: Extracted table as Markdown string
            - extraction_method: How the table was extracted
            - confidence: Confidence score (0-1)
            - error: Error message if extraction failed
    """
    image_path = Path(image_path)

    if not image_path.exists():
        return {
            "markdown": "",
            "extraction_method": "none",
            "confidence": 0.0,
            "error": f"Image file not found: {image_path}",
        }

    # If no provider, return empty
    if provider is None:
        return {
            "markdown": "",
            "extraction_method": "none",
            "confidence": 0.0,
            "error": "No Vision API provider configured",
        }

    # Default prompt for table extraction
    if prompt is None:
        prompt = _default_table_extraction_prompt()

    try:
        # Call the Vision API provider
        result = provider.describe_media(
            image_path=str(image_path),
            task_type="table_to_markdown",
            prompt=prompt,
        )

        if result.get("status") == "success":
            markdown = result.get("description", "")
            return {
                "markdown": markdown,
                "extraction_method": "vision_api",
                "confidence": 0.85,
                "error": None,
            }
        else:
            return {
                "markdown": "",
                "extraction_method": "vision_api_failed",
                "confidence": 0.0,
                "error": result.get("error", "Unknown error"),
            }

    except Exception as e:
        logger.error(f"Vision API table extraction failed: {e}")
        return {
            "markdown": "",
            "extraction_method": "vision_api_error",
            "confidence": 0.0,
            "error": str(e),
        }


def _default_table_extraction_prompt() -> str:
    """Get the default prompt for table extraction."""
    return """Please extract the table from this image and convert it to Markdown format.

Instructions:
1. Preserve the table structure with proper Markdown syntax (| for columns, - for header separator)
2. Include all rows and columns visible in the image
3. If there are merged cells, represent them appropriately
4. Keep the original text content as accurately as possible
5. If there are mathematical expressions, use LaTeX notation ($...$)

Output only the Markdown table, no additional text."""


def compute_prompt_hash(prompt: str) -> str:
    """Compute a hash of the prompt for caching/deduplication."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def extract_ocr_text(
    image_path: str | Path,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Extract OCR text from a table image.

    Args:
        image_path: Path to the table image
        provider: Vision API provider instance

    Returns:
        Dict with extracted text and metadata
    """
    image_path = Path(image_path)

    if not image_path.exists():
        return {
            "text": "",
            "extraction_method": "none",
            "error": f"Image file not found: {image_path}",
        }

    if provider is None:
        return {
            "text": "",
            "extraction_method": "none",
            "error": "No Vision API provider configured",
        }

    prompt = """Please extract all text content from this table image.

Instructions:
1. Read all text in the table cells
2. Preserve the logical order (row by row, left to right)
3. Include headers and data
4. If there are mathematical expressions, transcribe them accurately

Output the extracted text, preserving the table structure as much as possible."""

    try:
        result = provider.describe_media(
            image_path=str(image_path),
            task_type="describe_media",
            prompt=prompt,
        )

        if result.get("status") == "success":
            return {
                "text": result.get("description", ""),
                "extraction_method": "vision_api_ocr",
                "error": None,
            }
        else:
            return {
                "text": "",
                "extraction_method": "vision_api_failed",
                "error": result.get("error", "Unknown error"),
            }

    except Exception as e:
        logger.error(f"Vision API OCR failed: {e}")
        return {
            "text": "",
            "extraction_method": "vision_api_error",
            "error": str(e),
        }
