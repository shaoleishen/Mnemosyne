"""RAG agent state definition.

Defines the state shape used by the LangGraph RAG flow.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    """State for the RAG agent flow.

    Fields:
        query: The user's question
        topic: Optional topic filter
        paper_id: Optional paper ID filter
        raw_retrieved: Raw retrieval results from FTS/hybrid search
        context_texts: Physical text evidence (chunks, captions)
        context_media: Original media assets (figures, tables)
        auxiliary_context: Machine-extracted tables and VLM descriptions
        formatted_prompt: The formatted multimodal prompt
        final_response: Generated answer
        audit: Audit results including source type verification
        degraded_reason: Reason for degraded performance if any
    """
    query: str
    topic: str | None
    paper_id: str | None
    raw_retrieved: list[dict[str, Any]]
    context_texts: list[dict[str, Any]]
    context_media: list[dict[str, Any]]
    auxiliary_context: list[dict[str, Any]]
    formatted_prompt: Any
    final_response: str
    audit: dict[str, Any]
    degraded_reason: str | None
