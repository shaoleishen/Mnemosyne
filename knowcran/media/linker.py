"""Link media assets to body text mentions.

This module handles:
- Finding captions near figure/table elements
- Linking body text mentions to media assets
- Matching references like "Figure 1", "Fig. 1", "图1", "Table 1", "表1"
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from knowcran.media.extract import MediaAsset, normalize_label, _FIGURE_LABEL_PATTERNS, _TABLE_LABEL_PATTERNS
from knowcran.parsers.base import ParsedElement

logger = logging.getLogger(__name__)

# Combined patterns for matching references in body text
_MEDIA_REFERENCE_PATTERNS = [
    # English: Figure 1, Figures 1-3, Fig. 1, Fig. 1a
    re.compile(r"(?:Figures?|Figs?\.?)\s*(\d+[a-z]?)(?:\s*[-–]\s*(\d+[a-z]?))?", re.IGNORECASE),
    # English: Table 1, Tables 1-3
    re.compile(r"(?:Tables?)\s*(\d+[a-z]?)(?:\s*[-–]\s*(\d+[a-z]?))?", re.IGNORECASE),
    # Chinese: 图1, 图1-3, 图 1
    re.compile(r"图\s*(\d+[a-z]?)(?:\s*[-–]\s*(\d+[a-z]?))?"),
    # Chinese: 表1, 表1-3
    re.compile(r"表\s*(\d+[a-z]?)(?:\s*[-–]\s*(\d+[a-z]?))?"),
]

# Caption detection patterns - captions typically start with Figure/Table label
_CAPTION_PATTERNS = [
    re.compile(r"^((?:Figure|Fig\.?)\s*\d+[a-z]?\s*[:\.：].+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^(Table\s*\d+[a-z]?\s*[:\.：].+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^(图\s*\d+[a-z]?\s*[:\.：].+)"),
    re.compile(r"^(表\s*\d+[a-z]?\s*[:\.：].+)"),
]


@dataclass
class MediaMention:
    """Represents a mention of a media asset in body text."""
    mention_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    media_id: str = ""
    chunk_id: str = ""
    paper_id: str = ""
    mention_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "media_id": self.media_id,
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "mention_text": self.mention_text,
        }


def find_caption_for_figure(
    figure_element: ParsedElement,
    all_elements: list[ParsedElement],
    max_distance: int = 2,
) -> str | None:
    """Find the caption text for a figure/table element.

    Looks for caption text in nearby elements. Captions typically:
    - Appear immediately before or after the figure/table
    - Start with "Figure X:" or "Table X:"
    - Are longer than typical body text paragraphs

    Args:
        figure_element: The figure/table element
        all_elements: All parsed elements from the document
        max_distance: Maximum element index distance to search

    Returns:
        Caption text if found, None otherwise
    """
    # First, check if the element itself contains caption text
    for pattern in _CAPTION_PATTERNS:
        m = pattern.search(figure_element.text)
        if m:
            return m.group(1).strip()

    # Find elements near the figure
    figure_idx = figure_element.element_index
    figure_page = figure_element.page_idx

    # Get nearby elements on the same page
    nearby = [
        e for e in all_elements
        if e.page_idx == figure_page
        and abs(e.element_index - figure_idx) <= max_distance
        and e.element_id != figure_element.element_id
    ]

    # Sort by distance
    nearby.sort(key=lambda e: abs(e.element_index - figure_idx))

    for elem in nearby:
        # Check if this element looks like a caption
        for pattern in _CAPTION_PATTERNS:
            m = pattern.search(elem.text)
            if m:
                return m.group(1).strip()

        # Also check for caption-like text (starts with Figure/Table label)
        normalized = normalize_label(elem.text[:50])
        if normalized and len(elem.text) > 30:
            return elem.text.strip()

    return None


def extract_media_references(text: str) -> list[dict[str, str]]:
    """Extract media references from text.

    Returns list of dicts with 'type' (figure/table) and 'label' (normalized).
    """
    refs = []
    seen = set()

    for pattern in _MEDIA_REFERENCE_PATTERNS:
        for m in pattern.finditer(text):
            # Determine type from the matched text
            matched = m.group(0)
            if any(kw in matched.lower() for kw in ("figure", "fig", "图")):
                media_type = "figure"
            else:
                media_type = "table"

            # Get the number
            num = m.group(1)
            label = f"{'Figure' if media_type == 'figure' else 'Table'} {num}"

            if label not in seen:
                seen.add(label)
                refs.append({"type": media_type, "label": label})

            # Handle ranges (e.g., "Figures 1-3")
            if m.group(2):
                end_num = m.group(2)
                end_label = f"{'Figure' if media_type == 'figure' else 'Table'} {end_num}"
                if end_label not in seen:
                    seen.add(end_label)
                    refs.append({"type": media_type, "label": end_label})

    return refs


def link_media_mentions(
    media_assets: list[MediaAsset],
    text_elements: list[ParsedElement],
    chunk_map: dict[str, str] | None = None,
) -> list[MediaMention]:
    """Link media assets to body text mentions.

    This function:
    1. Builds a label -> media_id mapping from assets
    2. Scans text elements for references to figures/tables
    3. Creates MediaMention objects for each reference found

    Args:
        media_assets: List of extracted media assets
        text_elements: List of text elements (paragraphs, etc.)
        chunk_map: Optional mapping from element_id to chunk_id

    Returns:
        List of MediaMention objects
    """
    # Build label -> asset mapping
    label_to_asset: dict[str, MediaAsset] = {}
    for asset in media_assets:
        if asset.figure_label:
            label_to_asset[asset.figure_label] = asset

    mentions: list[MediaMention] = []
    seen: set[tuple[str, str]] = set()  # (media_id, chunk_id) pairs

    for element in text_elements:
        # Skip non-text elements
        if element.element_type in ("figure", "table", "image"):
            continue

        # Extract references from text
        refs = extract_media_references(element.text)

        for ref in refs:
            label = ref["label"]
            asset = label_to_asset.get(label)
            if not asset:
                continue

            # Determine chunk_id
            chunk_id = ""
            if chunk_map:
                chunk_id = chunk_map.get(element.element_id, "")

            # Avoid duplicates
            key = (asset.media_id, chunk_id or element.element_id)
            if key in seen:
                continue
            seen.add(key)

            # Extract the relevant mention text (sentence containing the reference)
            mention_text = _extract_mention_sentence(element.text, label)

            mentions.append(MediaMention(
                media_id=asset.media_id,
                chunk_id=chunk_id,
                paper_id=asset.paper_id,
                mention_text=mention_text,
            ))

    return mentions


def _extract_mention_sentence(text: str, label: str) -> str:
    """Extract the sentence containing a media reference.

    Falls back to the full text if sentence boundaries can't be determined.
    """
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?。！？])\s+', text)

    for sentence in sentences:
        if label.lower() in sentence.lower() or label.replace(" ", "").lower() in sentence.replace(" ", "").lower():
            return sentence.strip()

    # Fallback: return text around the label
    idx = text.lower().find(label.lower())
    if idx >= 0:
        start = max(0, idx - 100)
        end = min(len(text), idx + len(label) + 100)
        return text[start:end].strip()

    return text[:200].strip()


def find_caption_elements(
    elements: list[ParsedElement],
) -> dict[str, str]:
    """Find all caption elements and map labels to caption text.

    Returns dict mapping normalized label -> caption text.
    """
    captions: dict[str, str] = {}

    for elem in elements:
        for pattern in _CAPTION_PATTERNS:
            m = pattern.search(elem.text)
            if m:
                caption_text = m.group(1).strip()
                # Try to get the label
                label = normalize_label(caption_text[:30])
                if label:
                    captions[label] = caption_text
                break

    return captions
