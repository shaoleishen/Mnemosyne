"""Retrieval node for the RAG flow.

Performs FTS-prefiltered hybrid search and returns IDs plus metadata.
"""

from __future__ import annotations

import logging
from typing import Any

from knowcran.rag.state import AgentState
from knowcran.storage import Storage
from knowcran.config import Settings

logger = logging.getLogger(__name__)


def retrieve(state: AgentState, storage: Storage, settings: Settings) -> dict[str, Any]:
    """Retrieve relevant chunks and media using FTS-prefiltered hybrid search.

    This node:
    1. Performs FTS5 search to find candidate chunks
    2. Loads embeddings only for candidates
    3. Reranks using RRF
    4. Returns raw retrieved results

    Args:
        state: Current RAG agent state
        storage: Storage instance
        settings: Settings instance

    Returns:
        Updated state with raw_retrieved results
    """
    query = state["query"]
    topic = state.get("topic")
    paper_id = state.get("paper_id")

    logger.info(f"Retrieving for query: {query[:100]}...")

    # Use FTS-prefiltered hybrid search
    from knowcran.fulltext import fts_prefiltered_hybrid_search

    try:
        results = fts_prefiltered_hybrid_search(
            query=query,
            topic=topic,
            paper_id=paper_id,
            limit=20,
            fts_limit=100,
            storage=storage,
            settings=settings,
        )
        degraded_reason = results.degraded_reason if hasattr(results, "degraded_reason") else None
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        results = []
        degraded_reason = f"Retrieval failed: {e}"

    # Also search media assets if available
    media_results = []
    try:
        from knowcran.fulltext import multimodal_search
        multimodal = multimodal_search(
            query=query,
            topic=topic,
            paper_id=paper_id,
            limit=10,
            storage=storage,
            settings=settings,
        )
        media_results = multimodal.get("media", [])
    except Exception as e:
        logger.warning(f"Media search failed: {e}")

    # Combine results
    raw_retrieved = list(results) + media_results

    return {
        "raw_retrieved": raw_retrieved,
        "degraded_reason": degraded_reason,
    }
