"""Hydrate and filter node for the RAG flow.

Looks up real chunks/media from SQLite and separates physical evidence
from machine text based on the evidence contract.
"""

from __future__ import annotations

import logging
from typing import Any

from knowcran.rag.state import AgentState
from knowcran.storage import Storage

logger = logging.getLogger(__name__)

# Source types that are physical evidence (highest trust)
PHYSICAL_SOURCE_TYPES = {
    "physical_text",
    "physical_caption",
    "original_media",
}

# Source types that are auxiliary interpretation (lower trust)
AUXILIARY_SOURCE_TYPES = {
    "machine_extracted_table",
    "auxiliary_interpretation",
}


def hydrate_and_filter(state: AgentState, storage: Storage) -> dict[str, Any]:
    """Hydrate retrieved results and separate by evidence type.

    This node:
    1. Takes raw retrieved results
    2. Looks up full chunk/media data from SQLite
    3. Separates into physical evidence and auxiliary interpretation
    4. Returns context_texts, context_media, and auxiliary_context

    Args:
        state: Current RAG agent state
        storage: Storage instance

    Returns:
        Updated state with separated context
    """
    raw_retrieved = state.get("raw_retrieved", [])

    context_texts = []
    context_media = []
    auxiliary_context = []

    for item in raw_retrieved:
        source_type = item.get("source_type", "physical_text")

        # Determine category
        if source_type in PHYSICAL_SOURCE_TYPES:
            if source_type == "original_media":
                context_media.append(item)
            else:
                context_texts.append(item)
        elif source_type in AUXILIARY_SOURCE_TYPES:
            auxiliary_context.append(item)
        else:
            # Default to physical text for backward compatibility
            context_texts.append(item)

    # Hydrate media assets with full context
    hydrated_media = []
    for media in context_media:
        media_id = media.get("media_id")
        if media_id:
            full_context = storage.get_media_context(media_id)
            if full_context:
                hydrated_media.append({
                    **media,
                    "mentions": full_context.get("mentions", []),
                    "descriptions": full_context.get("descriptions", []),
                })
            else:
                hydrated_media.append(media)
        else:
            hydrated_media.append(media)

    # Hydrate auxiliary context with full descriptions
    hydrated_auxiliary = []
    for aux in auxiliary_context:
        media_id = aux.get("media_id")
        if media_id:
            descriptions = storage.get_media_vlm_descriptions(media_id)
            if descriptions:
                hydrated_auxiliary.append({
                    **aux,
                    "vlm_descriptions": descriptions,
                })
            else:
                hydrated_auxiliary.append(aux)
        else:
            hydrated_auxiliary.append(aux)

    logger.info(
        f"Hydrated: {len(context_texts)} text chunks, "
        f"{len(hydrated_media)} media assets, "
        f"{len(hydrated_auxiliary)} auxiliary items"
    )

    return {
        "context_texts": context_texts,
        "context_media": hydrated_media,
        "auxiliary_context": hydrated_auxiliary,
    }
