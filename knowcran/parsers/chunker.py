from __future__ import annotations

import hashlib
import json
import uuid
import logging
from typing import Any

from knowcran.parsers.base import ParsedElement

logger = logging.getLogger(__name__)

TARGET_CHUNK_MIN = 800
TARGET_CHUNK_MAX = 1400
OVERLAP_WORDS_TARGET = 200

def chunk_elements(elements: list[ParsedElement], paper_id: str, asset_id: str) -> list[dict[str, Any]]:
    """Chunk layout elements into semantic, page-aware chunks.
    
    Rules:
    - Target: 900-1400 words.
    - Boundaries: Never cross paper boundaries. Prefer to split on major section changes.
    - Overlap: Element-based overlap of ~200 words.
    - Metadata: Tracks page_start, page_end, section, and constituent elements.
    """
    if not elements:
        return []

    # Sort elements to ensure correct reading order (by page_idx, then element_index)
    sorted_elements = sorted(elements, key=lambda e: (e.page_idx, e.element_index))

    chunks = []
    chunk_index = 0
    current_elements: list[ParsedElement] = []
    current_words = 0
    current_section = None

    for el in sorted_elements:
        el_words = len(el.text.split())
        
        # Section transition check: if the section changes and we already have a reasonably sized chunk, flush it
        el_section = el.section or current_section
        section_changed = current_section is not None and el.section is not None and el.section != current_section

        if section_changed and current_words >= TARGET_CHUNK_MIN:
            # Flush current chunk before starting the new section
            chunks.append(_create_chunk(current_elements, paper_id, asset_id, current_section, chunk_index))
            chunk_index += 1
            
            # Start new chunk with element overlap from previous elements (if relevant to the same section, or just start fresh)
            # Since the section changed, starting fresh is usually better, but we can carry over if word count is small
            current_elements = []
            current_words = 0

        # Update current section
        if el.section:
            current_section = el.section

        # Check if adding this element exceeds the maximum size
        if current_words + el_words > TARGET_CHUNK_MAX and current_elements:
            # Flush current chunk
            chunks.append(_create_chunk(current_elements, paper_id, asset_id, current_section, chunk_index))
            chunk_index += 1

            # Build overlap: backtrack from the end of current_elements
            overlap_elements: list[ParsedElement] = []
            overlap_words = 0
            for prev_el in reversed(current_elements):
                prev_words = len(prev_el.text.split())
                if overlap_words + prev_words <= OVERLAP_WORDS_TARGET:
                    overlap_elements.insert(0, prev_el)
                    overlap_words += prev_words
                else:
                    break

            current_elements = overlap_elements + [el]
            current_words = overlap_words + el_words
        else:
            current_elements.append(el)
            current_words += el_words

    # Flush any remaining elements
    if current_elements:
        # If the last chunk is very small and we have previous chunks, try to merge it
        if current_words < TARGET_CHUNK_MIN and chunks:
            last_chunk = chunks[-1]
            # Verify they are from the same paper and same asset (always true here)
            merged_text = last_chunk["text"] + "\n\n" + "\n\n".join(e.text for e in current_elements)
            last_chunk["text"] = merged_text
            last_chunk["page_end"] = max(last_chunk["page_end"], max(e.page_idx + 1 for e in current_elements))
            last_chunk["text_hash"] = hashlib.sha256(merged_text.encode()).hexdigest()[:16]
            last_chunk["token_count"] = len(merged_text.split())
            
            # Merge element IDs
            try:
                el_ids = json.loads(last_chunk["element_ids_json"])
                el_ids.extend([e.element_id for e in current_elements])
                last_chunk["element_ids_json"] = json.dumps(el_ids)
            except Exception:
                pass
        else:
            chunks.append(_create_chunk(current_elements, paper_id, asset_id, current_section, chunk_index))

    return chunks

def _create_chunk(elements: list[ParsedElement], paper_id: str, asset_id: str, section: str | None, chunk_index: int) -> dict[str, Any]:
    """Helper to construct the chunk dictionary from elements."""
    text = "\n\n".join(e.text for e in elements)
    page_start = min(e.page_idx + 1 for e in elements)
    page_end = max(e.page_idx + 1 for e in elements)
    element_ids = [e.element_id for e in elements]
    
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    token_count = len(text.split())

    return {
        "chunk_id": str(uuid.uuid4()),
        "paper_id": paper_id,
        "asset_id": asset_id,
        "page_start": page_start,
        "page_end": page_end,
        "section": section,
        "chunk_index": chunk_index,
        "text": text,
        "text_hash": text_hash,
        "token_count": token_count,
        "element_ids_json": json.dumps(element_ids),
    }
